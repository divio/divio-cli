import json
import os
import re
import sys
from itertools import groupby
from netrc import netrc
from operator import itemgetter
from time import sleep
from urllib.parse import urlparse

import click
from dateutil.parser import isoparse

from . import api_requests, messages, settings
from .config import Config
from .localdev.utils import get_application_home, get_project_settings
from .utils import json_response_request_paginate


ENDPOINT = "https://control.{zone}"
DEFAULT_ZONE = "divio.com"


def get_divio_zone():
    try:
        application_specific_zone = get_project_settings(
            get_application_home()
        ).get("zone", None)
    except click.ClickException:
        # Happens when there is no configuration file
        pass
    else:
        if application_specific_zone:
            return application_specific_zone
    return os.environ.get("DIVIO_ZONE", DEFAULT_ZONE)


def get_endpoint(zone=None):
    if not zone:
        zone = get_divio_zone()
    if re.match("^https?://", zone):
        endpoint = zone
    else:
        endpoint = ENDPOINT.format(zone=zone)

    if zone != DEFAULT_ZONE:
        click.secho("Using zone: {}\n".format(endpoint), fg="green")
    return endpoint


def get_service_color(service):
    color_mapping = {
        "web": "blue",
        "cronjob": "bright_cyan",
        "shell": "bright_red",
        "worker": "bright_blue",
    }
    try:
        return color_mapping[service]
    except KeyError:
        return "yellow"


class CloudClient(object):
    def __init__(self, endpoint, debug=False, sudo=False):
        self.debug = debug
        self.sudo = sudo
        self.config = Config()
        self.endpoint = endpoint
        self.netrc = WritableNetRC()
        self.session = self.init_session()

    # Helpers
    def get_auth_header(self):
        host = urlparse(self.endpoint).hostname
        data = self.netrc.hosts.get(host)
        headers = {}
        if data:
            headers["Authorization"] = "Token {}".format(data[2])
        if self.sudo:
            headers["X-Sudo"] = "make me a sandwich"
        return headers

    def get_access_token_url(self):
        return "{}/{}".format(
            self.endpoint.rstrip("/"),
            settings.ACCESS_TOKEN_URL_PATH.lstrip("/"),
        )

    def init_session(self):
        return api_requests.SingleHostSession(
            self.endpoint,
            headers=self.get_auth_header(),
            trust_env=False,
            debug=self.debug,
        )

    def authenticate(self, token):
        self.session.headers["Authorization"] = "Token {}".format(token)

    def login(self, token):
        request = api_requests.LoginRequest(
            self.session, data={"token": token}
        )
        user_data = request()

        self.authenticate(token)

        first_name = user_data.get("first_name")
        last_name = user_data.get("last_name")
        email = user_data.get("email")

        if first_name and last_name:
            greeting = "{} {} ({})".format(first_name, last_name, email)
        elif first_name:
            greeting = "{} ({})".format(first_name, email)
        else:
            greeting = email

        self.netrc.add(urlparse(self.endpoint).hostname, email, None, token)
        self.netrc.write()

        return messages.LOGIN_SUCCESSFUL.format(greeting=greeting)

    def check_login_status(self):
        request = api_requests.LoginStatusRequest(self.session)
        response = request()

        user_id = response.get("user_id")

        if user_id:
            return True, messages.LOGIN_CHECK_SUCCESSFUL
        else:
            return False, messages.LOGIN_CHECK_ERROR

    def get_applications(self):
        request = api_requests.ProjectListRequest(self.session)
        return request()

    def ssh(self, website_id, environment):
        project_data = self.get_project(website_id)
        try:
            status = project_data["{}_status".format(environment)]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(
                    environment
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)
        if status["deployed_before"]:
            try:
                response = api_requests.EnvironmentRequest(
                    self.session,
                    url_kwargs={"environment_uuid": status["uuid"]},
                )()
                ssh_command = [
                    "ssh",
                    "-p",
                    str(response["ssh_endpoint"]["port"]),
                    "{}@{}".format(
                        response["ssh_endpoint"]["user"],
                        response["ssh_endpoint"]["host"],
                    ),
                ]
                click.secho(" ".join(ssh_command), fg="green")
                os.execvp("ssh", ssh_command)

            except (KeyError, json.decoder.JSONDecodeError):
                click.secho(
                    "Error establishing ssh connection.", fg="red", err=True
                )
                sys.exit(1)

        else:
            click.secho(
                "SSH connection not available: environment '{}' not deployed yet.".format(
                    environment
                ),
                fg="yellow",
                err=True,
            )
            sys.exit(1)

    def get_environment(self, website_id, environment):
        project_data = self.get_project(website_id)
        try:
            status = project_data["{}_status".format(environment)]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(
                    environment
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)
        try:
            response = api_requests.EnvironmentRequest(
                self.session,
                url_kwargs={"environment_uuid": status["uuid"]},
            )()
            return response

        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                "Error establishing connection.",
                fg="red",
                err=True,
            )
            sys.exit(1)

    def get_application(self, application_uuid):
        try:
            response = api_requests.ApplicationRequest(
                self.session,
                url_kwargs={"application_uuid": application_uuid},
            )()
            return response

        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                "Error establishing connection.",
                fg="red",
                err=True,
            )
            sys.exit(1)

    def show_log(self, website_id, environment, tail=False, utc=True):
        def print_log_data(data):
            for entry in data:
                dt = isoparse(entry["timestamp"])
                if not utc:
                    dt = dt.astimezone()
                click.secho(
                    "{} \u2502 {:^16} \u2502 {}".format(
                        str(dt),
                        click.style(
                            entry["service"],
                            fg=get_service_color(entry["service"]),
                        ),
                        entry["message"]
                        .replace("\r", "")
                        .replace("\x1b[6n", "")
                        .replace("\x1b[J", "")
                        .replace("\x1b[H", ""),
                    )
                )

        project_data = self.get_project(website_id)
        try:
            status = project_data["{}_status".format(environment)]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(
                    environment
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)
        if status["deployed_before"]:
            try:
                # Make the initial log request
                response = api_requests.LogRequest(
                    self.session,
                    url_kwargs={"environment_uuid": status["uuid"]},
                )()

                print_log_data(response["results"])

                if tail:
                    # Now continue to poll
                    try:
                        while True:
                            # In this case, we can not construct the urls anymore and we have to rely on the previous response we got
                            response = self.session.request(
                                url=response["next"], method="GET"
                            ).json()

                            print_log_data(response["results"])
                            if not response["results"]:
                                sleep(1)
                    except (KeyboardInterrupt, SystemExit):
                        click.secho("Exiting...")
                        sys.exit(1)
            except (
                KeyError,
                json.decoder.JSONDecodeError,
                api_requests.APIRequestError,
            ):
                click.secho("Error retrieving logs.", fg="red", err=True)
                sys.exit(1)

        else:
            click.secho(
                "Logs not available: environment '{}' not deployed yet.".format(
                    environment
                ),
                fg="yellow",
                err=True,
            )
            sys.exit(1)

    def get_deploy_log(self, website_id, env_name):
        environment = self.get_environment(website_id, env_name)
        if environment:
            last_deployment_uuid = None
            try:
                last_deployment_uuid = environment["last_finished_deployment"][
                    "uuid"
                ]
            except (TypeError, KeyError):
                click.secho(
                    f"No finished deployment found in environemnt '{env_name}'.",
                    fg="yellow",
                )

            if last_deployment_uuid:
                try:
                    deploy_log = api_requests.DeployLogRequest(
                        self.session,
                        url_kwargs={"deployment_uuid": last_deployment_uuid},
                    )()
                    output = f"Deployment ID: {deploy_log['uuid']}\n\n{deploy_log['logs']}"
                    return output

                except json.decoder.JSONDecodeError:
                    click.secho(
                        "Error in fetching deployment logs.",
                        fg="red",
                        err=True,
                    )
                    sys.exit(1)
        else:
            click.secho(
                f"Environment with name {env_name} does not exist.",
                fg="yellow",
            )

    def deploy_application_or_get_progress(self, website_id, environment):
        def fmt_progress(data):
            if not data:
                return "Connecting to remote"
            if isinstance(data, dict):
                return "{} ({})".format(
                    data.get("verbose_state", "..."),
                    data.get("heartbeat_ago_formatted", "?"),
                )
            return data

        response = self.deploy_project_progress(website_id, environment)
        if response["is_deploying"]:
            click.secho(
                "Already deploying {} environment, attaching to running "
                "deployment".format(environment),
                fg="yellow",
            )
        else:
            click.secho(
                "Deploying {} environment".format(environment), fg="green"
            )
            self.deploy_project(website_id, environment)
            sleep(1)
            response = self.deploy_project_progress(website_id, environment)
        try:
            with click.progressbar(
                length=100,
                show_percent=True,
                show_eta=False,
                item_show_func=fmt_progress,
            ) as bar:
                progress_percent = 0
                while response["is_deploying"]:
                    response = self.deploy_project_progress(
                        website_id, environment
                    )
                    bar.current_item = progress = response["deploy_progress"]
                    if (
                        "main_percent" in progress
                        and "extra_percent" in progress
                    ):
                        # update the difference of the current percentage
                        # to the new percentage
                        progress_percent = (
                            progress["main_percent"]
                            + progress["extra_percent"]
                            - bar.pos
                        )
                        bar.update(progress_percent)
                    sleep(3)
                if response["last_deployment"]["status"] == "failure":
                    bar.current_item = "error"
                    bar.update(progress_percent)

                    raise click.ClickException(
                        "\nDeployment failed. Please run 'divio app deploy-log {}' "
                        "to get more information".format(environment)
                    )
                else:
                    bar.current_item = "Done"
                    bar.update(100)

        except KeyboardInterrupt:
            click.secho("Disconnected")

    def deploy_project_progress(self, website_id, environment):
        request = api_requests.DeployProjectProgressRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        data = request()
        try:
            return data[environment]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(
                    environment
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)

    def deploy_project(self, website_id, environment):
        data = {"stage": environment}
        request = api_requests.DeployProjectRequest(
            self.session, url_kwargs={"website_id": website_id}, data=data
        )
        return request()

    def get_project(self, website_id):
        request = api_requests.ProjectDetailRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        return request()

    def register_addon(self, package_name, verbose_name, organisation_id=None):
        request = api_requests.RegisterAddonRequest(
            self.session,
            data={
                "package_name": package_name,
                "name": verbose_name,
                "organisation": organisation_id,
            },
        )
        return request()

    def upload_addon(self, archive_obj):
        request = api_requests.UploadAddonRequest(
            self.session, files={"app": archive_obj}
        )
        return request()

    def upload_boilerplate(self, archive_obj):
        request = api_requests.UploadBoilerplateRequest(
            self.session, files={"boilerplate": archive_obj}
        )
        return request()

    def get_website_id_for_slug(self, slug):
        request = api_requests.SlugToIDRequest(
            self.session, url_kwargs={"website_slug": slug}
        )
        return request()

    def download_backup(self, website_slug, filename=None, directory=None):
        request = api_requests.DownloadBackupRequest(
            self.session,
            url_kwargs={"website_slug": website_slug},
            filename=filename,
            directory=directory,
        )
        return request()

    def download_db_request(self, website_id, environment, prefix):
        request = api_requests.DownloadDBRequestRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": environment, "prefix": prefix},
        )
        return request()

    def download_db_progress(self, url):
        request = api_requests.DownloadDBProgressRequest(self.session, url=url)
        return request()

    def download_media_request(self, website_id, environment):
        request = api_requests.DownloadMediaRequestRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": environment},
        )
        return request()

    def download_media_progress(self, url):
        request = api_requests.DownloadMediaProgressRequest(
            self.session, url=url
        )
        return request()

    def upload_db(self, website_id, environment, archive_path, prefix):
        request = api_requests.UploadDBRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": environment, "prefix": prefix},
            files={"db_dump": open(archive_path, "rb")},
        )
        return request()

    def upload_db_progress(self, url):
        request = api_requests.UploadDBProgressRequest(self.session, url=url)
        return request()

    def upload_media(
        self, website_id, environment, archive_path, prefix="DEFAULT"
    ):
        request = api_requests.UploadMediaFilesRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": environment, "prefix": prefix},
            files={"media_files": open(archive_path, "rb")},
        )
        return request()

    def upload_media_progress(self, url):
        request = api_requests.UploadMediaFilesProgressRequest(
            self.session, url=url
        )
        return request()

    def list_deployments(
        self,
        website_id,
        environment,
        all_environments,
        limit_results,
    ):
        project_data = self.get_project(website_id)

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            project_data[key]["uuid"]: project_data[key]["stage"]
            for key in project_data.keys()
            if key.endswith("_status")
        }

        # Limit results to application deployments by default
        # and allow to filter by environment.
        params = {"application": project_data["uuid"]}

        # Retrieve environment data if environment is provided.
        if not all_environments:
            try:
                env = project_data[f"{environment}_status"]
                params.update({"environment": env["uuid"]})
            except KeyError:
                click.secho(
                    f"Environment with the name {environment!r} does not exist.",
                    fg="red",
                    err=True,
                )
                sys.exit(1)

        try:
            results, messages = json_response_request_paginate(
                api_requests.DeploymentsRequest,
                self.session,
                params=params,
                limit_results=limit_results,
            )

            if results:
                # Sort deployments by environment (necessary for groupby to be applied)
                results = sorted(results, key=itemgetter("environment"))
                # Group deployments by environment
                results_grouped_by_environment = [
                    {
                        "environment": envs_uuid_slug_mapping[key],
                        "environment_uuid": key,
                        "deployments": list(value),
                    }
                    for key, value in groupby(
                        results, itemgetter("environment")
                    )
                ]
            else:
                no_deployments_found_msg = (
                    "No deployments found for this application."
                    if all_environments
                    else f"No deployments found for {environment!r} environment."
                )
                click.secho(
                    no_deployments_found_msg,
                    fg="yellow",
                )
                sys.exit(0)
        except json.decoder.JSONDecodeError:
            click.secho(
                "Error in fetching deployments.",
                fg="red",
                err=True,
            )
            sys.exit(1)

        return results_grouped_by_environment, messages

    def get_deployment(
        self,
        website_id,
        deployment_uuid,
    ):
        project_data = self.get_project(website_id)

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            project_data[key]["uuid"]: project_data[key]["stage"]
            for key in project_data.keys()
            if key.endswith("_status")
        }

        try:
            deployment = api_requests.DeploymentRequest(
                self.session,
                url_kwargs={"deployment_uuid": deployment_uuid},
            )()
            environment_uuid = deployment["environment"]
            # This also provides a sanity check for the deployment_uuid.
            # E.g. The user asks for a deployment by providing a uuid
            # which belongs to a deployment of an environment on a
            # completely different application. Will trigger a KeyError.
            environment_slug = envs_uuid_slug_mapping[environment_uuid]
            deployment.pop("environment")
        except (json.decoder.JSONDecodeError, KeyError):
            click.secho(
                "Error in fetching deployment.",
                fg="red",
                err=True,
            )
            sys.exit(1)

        return {
            "environment": environment_slug,
            "environment_uuid": environment_uuid,
            "deployment": deployment,
        }

    def get_deployment_with_environment_variables(
        self,
        website_id,
        deployment_uuid,
        variable_name,
    ):
        project_data = self.get_project(website_id)

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            project_data[key]["uuid"]: project_data[key]["stage"]
            for key in project_data.keys()
            if key.endswith("_status")
        }

        try:
            deployment = api_requests.DeploymentEnvironmentVariablesRequest(
                self.session,
                url_kwargs={"deployment_uuid": deployment_uuid},
            )()
            environment_uuid = deployment["environment"]
            # This also provides a sanity check for the deployment_uuid.
            # E.g. The user asks for a deployment by providing a uuid
            # which belongs to a deployment of an environment on a
            # completely different application. Will trigger a KeyError.
            environment_slug = envs_uuid_slug_mapping[environment_uuid]
            deployment.pop("environment")

            value = deployment["environment_variables"].get(variable_name)
            if value is None:
                click.secho(
                    f"There is no environment variable named {variable_name!r} for this deployment.",
                    fg="yellow",
                )
                sys.exit(0)
        except (json.decoder.JSONDecodeError, KeyError):
            click.secho(
                "Error in fetching deployment.",
                fg="red",
                err=True,
            )
            sys.exit(1)

        return {
            "environment": environment_slug,
            "environment_uuid": environment_uuid,
            "deployment": deployment,
        }

    def list_environment_variables(
        self,
        website_id,
        environment,
        all_environments,
        limit_results,
        variable_name=None,
    ):
        project_data = self.get_project(website_id)

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            project_data[key]["uuid"]: project_data[key]["stage"]
            for key in project_data.keys()
            if key.endswith("_status")
        }

        # The environment variables V3 endpoint requires either
        # an application or an environment or both to be present
        # as query parameters. Multiple environments can be provided as well.
        if all_environments:
            params = {"application": project_data["uuid"]}
        else:
            environment_key = f"{environment}_status"
            if environment_key in project_data.keys():
                params = {"environment": project_data[environment_key]["uuid"]}
            else:
                click.secho(
                    "Environment with the name '{}' does not exist.".format(
                        environment
                    ),
                    fg="red",
                    err=True,
                )
                sys.exit(1)

        if variable_name:
            params.update({"name": variable_name})

        results, messages = json_response_request_paginate(
            api_requests.GetEnvironmentVariablesRequest,
            self.session,
            params=params,
            limit_results=limit_results,
        )

        if results:
            # Sort environment variables by environment (necessary for groupby to be applied)
            results = sorted(results, key=itemgetter("environment"))
            # Group environment variables by environment
            results_grouped_by_environment = [
                {
                    "environment": envs_uuid_slug_mapping[key],
                    "environment_uuid": key,
                    "environment_variables": list(value),
                }
                for key, value in groupby(results, itemgetter("environment"))
            ]
        else:
            if variable_name:
                no_environment_variables_found_msg = (
                    f"No environment variable named {variable_name!r} found for this application."
                    if all_environments
                    else f"No environment variable named {variable_name!r} found for {environment!r} environment."
                )
            else:
                no_environment_variables_found_msg = (
                    "No environment variables found for this application."
                    if all_environments
                    else f"No environment variables found for {environment!r} environment."
                )
            click.secho(
                no_environment_variables_found_msg,
                fg="yellow",
            )
            sys.exit(0)

        return results_grouped_by_environment, messages

    def get_repository_dsn(self, website_id):
        """
        Try to return the DSN of a remote repository for a given website_id.
        """
        try:
            request = api_requests.RepositoryRequest(
                self.session, url_kwargs={"website_id": website_id}
            )
            response = request()
            return response["results"][0]["backend_config"]["repository_dsn"]

        except IndexError:
            # happens when there is no remote repository configured
            return None

        raise click.ClickException(
            "Could not get remote repository information."
        )

    def get_regions(self):
        request = api_requests.ListRegionsRequest(self.session)
        return request()

    def get_organisations(self):
        request = api_requests.ListOrganisationsRequest(self.session)
        return request()


class WritableNetRC(netrc):
    def __init__(self, *args, **kwargs):
        netrc_path = self.get_netrc_path()
        if not os.path.exists(netrc_path):
            open(netrc_path, "a").close()
            os.chmod(netrc_path, 0o600)
        kwargs["file"] = netrc_path
        try:
            netrc.__init__(self, *args, **kwargs)
        except IOError:
            raise click.ClickException(
                "Please make sure your netrc config file ('{}') can be read "
                "and written by the current user.".format(netrc_path)
            )

    def get_netrc_path(self):
        """
        netrc uses os.environ['HOME'] for path detection which is
        not defined on Windows. Detecting the correct path ourselves
        """
        home = os.path.expanduser("~")
        return os.path.join(home, ".netrc")

    def add(self, host, login, account, password):
        self.hosts[host] = (login, account, password)

    def remove(self, host):
        if host in self.hosts:
            del self.hosts[host]

    def write(self, path=None):
        if path is None:
            path = self.get_netrc_path()

        out = []
        for machine, data in self.hosts.items():
            login, account, password = data
            out.append("machine {}".format(machine))
            if login:
                out.append("\tlogin {}".format(login))
            if account:
                out.append("\taccount {}".format(account))
            if password:
                out.append("\tpassword {}".format(password))

        with open(path, "w") as f:
            f.write(os.linesep.join(out))
