from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from itertools import groupby
from operator import itemgetter
from time import sleep
from urllib.parse import urlparse

import click
import requests
from dateutil.parser import isoparse

from divio_cli.exceptions import (
    ApplicationUUIDNotFoundException,
    ConfigurationNotFound,
    DivioException,
    DivioWarning,
    EnvironmentDoesNotExist,
)

from . import api_requests, messages, settings
from .config import Config, WritableNetRC
from .localdev.utils import get_application_home, get_project_settings
from .utils import json_response_request_paginate


ENDPOINT = "https://control.{zone}"
DEFAULT_ZONE = "divio.com"

logger = logging.getLogger("divio.client")


def get_divio_zone():
    try:
        application_specific_zone = get_project_settings(
            get_application_home()
        ).get("zone", None)
    except ConfigurationNotFound:
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
        logger.debug("using zone: %s", endpoint)
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


class CloudClient:
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
            headers["Authorization"] = f"Token {data[2]}"
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
        self.session.headers["Authorization"] = f"Token {token}"

    def login(self, token):
        request = api_requests.GetCurrentUserRequest(
            self.session,
            headers={
                "Authorization": f"Token {token}",
            },
        )

        user_data = request()

        self.authenticate(token)

        first_name = user_data.get("first_name")
        last_name = user_data.get("last_name")
        email = user_data.get("email")

        if first_name and last_name:
            greeting = f"{first_name} {last_name} ({email})"
        elif first_name:
            greeting = f"{first_name} ({email})"
        else:
            greeting = email

        self.netrc.add(urlparse(self.endpoint).hostname, email, None, token)
        self.netrc.write()

        return messages.LOGIN_SUCCESSFUL.format(greeting=greeting)

    def logout(self, interactive=True):
        def secho(*args, **kwargs):
            if not interactive:
                return None

            return click.secho(*args, **kwargs)

        def confirm(*args, **kwargs):
            if not interactive:
                return True

            return click.confirm(*args, **kwargs)

        host = urlparse(self.endpoint).hostname

        if host not in self.netrc.hosts:
            secho(messages.LOGOUT_ERROR.format(host), fg="red")

            return 1

        if not confirm(messages.LOGOUT_CONFIRMATION.format(host)):
            return 1

        self.netrc.remove(host)
        self.netrc.write()

        secho(messages.LOGOUT_SUCCESS.format(host))

        return 0

    def check_login_status(self):
        request = api_requests.GetCurrentUserRequest(self.session)
        response = request()

        user_id = response.get("uuid")

        if user_id:
            return True, messages.LOGIN_CHECK_SUCCESSFUL
        else:
            return False, messages.LOGIN_CHECK_ERROR

    def get_applications_v1(self):
        request = api_requests.ProjectListRequest(self.session)
        return request()

    def get_applications(self):
        results, messages = json_response_request_paginate(
            api_requests.ApplicationsListRequest,
            self.session,
            limit_results=None,
        )

        return results, messages

    def get_organisations(self, limit_results=None):
        results, messages = json_response_request_paginate(
            api_requests.ListOrganisationsRequest,
            self.session,
            limit_results=limit_results,
        )

        return results, messages

    def get_regions(self, limit_results=None, params=None):
        if params is None:
            params = {}
        results, messages = json_response_request_paginate(
            api_requests.ListRegionsRequest,
            self.session,
            params=params,
            limit_results=limit_results,
        )
        return results, messages

    def get_application_plan_groups(self, params=None):
        if params is None:
            params = {}
        results, messages = json_response_request_paginate(
            api_requests.ApplicationPlanGroupsListRequest,
            self.session,
            params=params,
            limit_results=None,
        )
        return results, messages

    def get_application_plan_group(self, plan_group_uuid):
        request = api_requests.ApplicationPlanGroupGetRequest(
            self.session,
            url_kwargs={"plan_group_uuid": plan_group_uuid},
        )
        return request()

    def get_application(self, application_uuid):
        try:
            return api_requests.ApplicationRequest(
                self.session,
                url_kwargs={"application_uuid": application_uuid},
            )()

        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                "Error establishing connection.",
                fg="red",
                err=True,
            )
            sys.exit(1)

    def get_application_templates(self, limit_results=None):
        results, messages = json_response_request_paginate(
            api_requests.ApplicationTemplateListRequest,
            self.session,
            limit_results=limit_results,
        )
        return results, messages

    def get_application_template(self, template_uuid):
        request = api_requests.ApplicationTemplateGetRequest(
            self.session,
            url_kwargs={"template_uuid": template_uuid},
        )
        return request()

    def application_create(self, data):
        try:
            return api_requests.CreateApplicationRequest(
                self.session,
                data=data,
            )()
        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                "Error establishing connection.",
                fg="red",
                err=True,
            )
            sys.exit(1)

    def get_organisation(self, organisation_uuid):
        request = api_requests.OrganisationDetailRequest(
            self.session,
            url_kwargs={"organisation_uuid": organisation_uuid},
        )
        return request()

    def get_services(
        self, region_uuid=None, application_uuid=None, limit_results=None
    ):
        kwargs = {}

        # TODO this smells like a security issue
        kwargs["filter_region"] = (
            f"region={region_uuid}" if region_uuid else ""
        )

        kwargs["filter_website"] = (
            f"website={application_uuid}" if application_uuid else ""
        )

        results, messages = json_response_request_paginate(
            api_requests.ListServicesRequest,
            self.session,
            url_kwargs=kwargs,
            limit_results=limit_results,
        )
        return results, messages

    def get_service_instances(self, environment_uuid, limit_results=None):
        results, messages = json_response_request_paginate(
            api_requests.ListServiceInstancesRequest,
            self.session,
            url_kwargs={"environment_uuid": environment_uuid},
            limit_results=limit_results,
        )
        return results, messages

    def add_service_instances(
        self, environment_uuid, prefix, region_uuid, service_uuid
    ):
        request = api_requests.CreateServiceInstanceRequest(
            self.session,
            data={
                "environment": environment_uuid,
                "region": region_uuid,
                "service": service_uuid,
                "prefix": prefix,
            },
        )
        return request()

    def ssh(self, application_uuid, environment):
        self.get_project(application_uuid)
        try:
            env = self.get_environment_by_application(
                application_uuid, environment
            )

        except KeyError:
            raise EnvironmentDoesNotExist(environment)

        if env["last_finished_deployment"]:
            try:
                response = api_requests.EnvironmentRequest(
                    self.session,
                    url_kwargs={"environment_uuid": env["uuid"]},
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
                raise DivioException("Error establishing ssh connection.")

        else:
            raise DivioException(
                f"SSH connection not available: environment '{environment}' not deployed yet.",
                fg="yellow",
            )

    def get_environment_by_application(self, application_uuid, environment):
        response = api_requests.EnvironmentsListRequest(
            self.session,
            params={
                "application": application_uuid,
                "slug": environment,
            },
        )()
        return response["results"][0]

    def get_environment(self, application_uuid, environment):
        try:
            env = self.get_environment_by_application(
                application_uuid, environment
            )
        except KeyError:
            raise EnvironmentDoesNotExist(environment)

        try:
            return api_requests.EnvironmentRequest(
                self.session,
                url_kwargs={"environment_uuid": env["uuid"]},
            )()

        except (KeyError, json.decoder.JSONDecodeError):
            raise DivioException("Error establishing connection.")

    def get_environments(self, params=None):
        if params is None:
            params = {}
        try:
            return api_requests.EnvironmentsListRequest(
                self.session, params=params
            )()
        except (KeyError, json.decoder.JSONDecodeError):
            raise DivioException("Error establishing connection.")

    def show_log(self, application_uuid, environment, tail=False, utc=True):
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

        try:
            env = self.get_environment_by_application(
                application_uuid, environment
            )
        except KeyError:
            raise EnvironmentDoesNotExist(environment)

        if env["last_finished_deployment"]:
            try:
                # Make the initial log request
                response = api_requests.LogRequest(
                    self.session,
                    url_kwargs={"environment_uuid": env["uuid"]},
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
                        raise DivioException("Exiting...", fg=None)
            except (
                KeyError,
                json.decoder.JSONDecodeError,
                api_requests.APIRequestError,
            ):
                raise DivioException("Error retrieving logs.")

        else:
            raise DivioException(
                f"Logs not available: environment '{environment}' not deployed yet.",
                fg="yellow",
            )

    def get_deploy_log(self, application_uuid, env_name):
        environment = self.get_environment(application_uuid, env_name)
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
                    return f"Deployment ID: {deploy_log['uuid']}\n\n{deploy_log['logs']}"

                except json.decoder.JSONDecodeError:
                    raise DivioException("Error in fetching deployment logs.")
            return None
        else:
            click.secho(
                f"Environment with name {env_name} does not exist.",
                fg="yellow",
            )
            return None

    def deploy_application_or_get_progress(
        self, application_uuid, environment, build_mode
    ):
        def fmt_progress(data):
            if not data:
                return "Connecting to remote"
            if isinstance(data, dict):
                return "{} ({})".format(
                    data.get("verbose_state", "..."),
                    data.get("heartbeat_ago_formatted", "?"),
                )
            return data

        try:
            env = self.get_environment_by_application(
                application_uuid, environment
            )
        except KeyError:
            raise EnvironmentDoesNotExist(environment)

        try:
            response = self.get_deployment_by_application(
                application_uuid, env["uuid"]
            )
            response = self.get_deployment_by_uuid(response["uuid"])
        except IndexError:
            response = None

        if response and response["ended_at"] is None:
            click.secho(
                f"Already deploying {environment} environment, attaching to running "
                "deployment",
                fg="yellow",
            )
        else:
            click.secho(f"Deploying {environment} environment", fg="green")
            deployment = self.deploy_project(env["uuid"], build_mode)
            sleep(1)
            response = self.get_deployment_by_uuid(deployment["uuid"])
        try:
            with click.progressbar(
                length=100,
                show_percent=True,
                show_eta=False,
                item_show_func=fmt_progress,
            ) as bar:
                progress_percent = 0
                while response["ended_at"] is None:
                    progress_percent = response["percent"]
                    response = self.get_deployment_by_uuid(response["uuid"])
                    bar.current_item = response["status"]
                    bar.update(progress_percent - bar.pos)
                    sleep(3)
                if not response["success"]:
                    bar.current_item = "error"
                    bar.update(progress_percent)

                    raise DivioException(
                        "\nDeployment failed. Please run "
                        f"'divio app deploy-log {environment}' "
                        "to get more information"
                    )

                bar.current_item = "Done"
                bar.update(100)

        except KeyboardInterrupt:
            click.secho("Disconnected")

    def get_deployment_by_application(
        self, application_uuid, environment_uuid
    ):
        request = api_requests.DeploymentByApplicationRequest(
            self.session,
            url_kwargs={
                "application_uuid": application_uuid,
                "environment_uuid": environment_uuid,
            },
        )
        return request()

    def deploy_environment(self, environment_uuid):
        request = api_requests.DeployEnvironmentRequest(
            self.session, data={"environment": environment_uuid}
        )
        return request()

    def get_deployment_by_uuid(self, deployment_uuid):
        request = api_requests.DeploymentRequest(
            self.session,
            url_kwargs={
                "deployment_uuid": deployment_uuid,
            },
        )
        return request()

    def deploy_project(self, environment_uuid, build_mode):
        data = {"environment": environment_uuid, "build_mode": build_mode}
        request = api_requests.DeployProjectRequest(self.session, data=data)
        return request()

    def get_project(self, application_uuid):
        request = api_requests.ProjectDetailRequest(
            self.session, url_kwargs={"application_uuid": application_uuid}
        )
        return request()

    def get_addon_uuid_for_package_name(self, package_name):
        response = api_requests.AddonPackageNameToUUIDRequest(
            session=self.session,
            url_kwargs={
                "package_name": package_name,
            },
        )()

        if "results" not in response or len(response["results"]) != 1:
            raise DivioException(
                f"Unable to retrieve an addon UUID for package name '{package_name}'"
            )

        return response["results"][0]["uuid"]

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

    def upload_addon(self, package_name, archive_obj):
        addon_uuid = self.get_addon_uuid_for_package_name(package_name)

        request = api_requests.UploadAddonRequest(
            self.session,
            url_kwargs={"addon_uuid": addon_uuid},
            files={"app": archive_obj},
        )

        return request()

    def get_application_uuid_for_slug(self, slug):
        response = api_requests.SlugToAppUUIDRequest(
            self.session, url_kwargs={"website_slug": slug}
        )()

        if "results" not in response or len(response["results"]) != 1:
            raise DivioException(
                f"Unable to retrieve an application UUID for slug '{slug}'"
            )

        return response["results"][0]["uuid"]

    def get_application_uuid_for_remote_id(self, remote_id):
        """
        Translate remote id to application UUID
        """

        response = api_requests.LegacyListApplicationsRequest(
            session=self.session, url_kwargs={"id": remote_id}
        )()

        if "results" not in response or len(response["results"]) != 1:
            raise DivioException(
                f"Unable to retrieve an application UUID for remote id '{remote_id}'"
            )

        return response["results"][0]["uuid"]

    def get_application_uuid(self, application_uuid_or_remote_id=None):
        """
        Takes an application uuid, remote id or no input, and trys to find
        the applications uuid, either from the given input or the project
        settings.
        """

        if application_uuid_or_remote_id:
            # legacy remote-id
            # remote-ids in .divio/config.json are stored as int
            # remote-ids issued via `--remote-id` come in as str
            if (
                isinstance(application_uuid_or_remote_id, int)
                or application_uuid_or_remote_id.isdigit()
            ):
                return self.get_application_uuid_for_remote_id(
                    remote_id=application_uuid_or_remote_id,
                )

        # retrieve application UUID or project id from project settings
        else:
            project_settings = get_project_settings(silent=True)

            if "application_uuid" in project_settings:
                return project_settings["application_uuid"]

            if "id" in project_settings:
                return self.get_application_uuid(
                    application_uuid_or_remote_id=str(project_settings["id"]),
                )

            raise ApplicationUUIDNotFoundException(
                f"Unable to retrieve an application UUID from '{application_uuid_or_remote_id}'",
            )

        # application UUID
        return application_uuid_or_remote_id

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

    def get_deployments(
        self,
        application_uuid,
        environment,
        all_environments,
        limit_results,
    ):
        environment_response = api_requests.EnvironmentsListRequest(
            self.session,
            params={
                "application": application_uuid,
            },
        )()["results"]

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            env["uuid"]: env["slug"] for env in environment_response
        }

        # Limit results to application deployments by default
        # and allow to filter by environment.
        params = {"application": application_uuid}

        # Retrieve environment data if environment is provided.
        if not all_environments:
            env_found = False
            for retrieved_env in environment_response:
                if retrieved_env["slug"] == environment:
                    params.update({"environment": retrieved_env["uuid"]})
                    env_found = True
                    break

            if not env_found:
                click.secho(
                    f"Environment with the name {environment!r} does not exist.",
                    fg="red",
                    err=True,
                )
            try:
                env = self.get_environment_by_application(
                    application_uuid, environment
                )

                params.update({"environment": env["uuid"]})
            except KeyError:
                raise EnvironmentDoesNotExist(environment)

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
                raise DivioWarning(no_deployments_found_msg)
        except json.decoder.JSONDecodeError:
            raise DivioException("Error in fetching deployments.")

        return results_grouped_by_environment, messages

    def get_deployment(
        self,
        application_uuid,
        deployment_uuid,
    ):
        environment_response = api_requests.EnvironmentsListRequest(
            self.session,
            params={
                "application": application_uuid,
            },
        )()["results"]

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            env["uuid"]: env["slug"] for env in environment_response
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
            raise DivioException("Error in fetching deployment.")

        return {
            "environment": environment_slug,
            "environment_uuid": environment_uuid,
            "deployment": deployment,
        }

    def get_deployment_with_environment_variables(
        self,
        application_uuid,
        deployment_uuid,
        variable_name,
    ):
        environment_response = api_requests.EnvironmentsListRequest(
            self.session,
            params={
                "application": application_uuid,
            },
        )()["results"]

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            env["uuid"]: env["slug"] for env in environment_response
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
                raise DivioWarning(
                    f"There is no environment variable named {variable_name!r} for this deployment.",
                )
        except (json.decoder.JSONDecodeError, KeyError):
            raise DivioException("Error in fetching deployment.")

        return {
            "environment": environment_slug,
            "environment_uuid": environment_uuid,
            "deployment": deployment,
        }

    def get_environment_variables(
        self,
        application_uuid,
        environment,
        all_environments,
        limit_results,
        variable_name=None,
    ):
        environment_response = api_requests.EnvironmentsListRequest(
            self.session,
            params={
                "application": application_uuid,
            },
        )()["results"]

        # Map environments uuids with their corresponding slugs.
        envs_uuid_slug_mapping = {
            env["uuid"]: env["slug"] for env in environment_response
        }

        # The environment variables V3 endpoint requires either
        # an application or an environment or both to be present
        # as query parameters. Multiple environments can be provided as well.
        if all_environments:
            params = {"application": application_uuid}
        else:
            params = {}
            env_found = False
            for retrieved_env in environment_response:
                if retrieved_env["slug"] == environment:
                    params.update({"environment": retrieved_env["uuid"]})
                    env_found = True
                    break
            if not env_found:
                raise EnvironmentDoesNotExist(environment)

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
            raise DivioWarning(no_environment_variables_found_msg)

        return results_grouped_by_environment, messages

    def create_repository(
        self,
        organisation,
        url,
        auth_type,
        ssh_key_type=None,
        host_username=None,
        host_password=None,
    ):
        data = {
            "organisation": organisation,
            "url": url,
        }

        if auth_type == "ssh":
            data["key_type"] = ssh_key_type
        else:
            data["username"] = host_username
            data["password"] = host_password

        return api_requests.CreateRepositoryRequest(
            self.session,
            data=data,
        )()

    def get_repository(self, repository_uuid):
        return api_requests.RepositoryRequest(
            self.session,
            url_kwargs={"repository_uuid": repository_uuid},
        )()

    def check_repository(self, repository_uuid, branch, migrate="true"):
        try:
            return api_requests.CheckRepositoryRequest(
                self.session,
                url_kwargs={"repository_uuid": repository_uuid},
                data={
                    "branch": branch,
                    "migrate": migrate,
                },
                proceed_on_4xx=True,
            )()
        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                "Error establishing connection while authenticating repository.",
                fg="red",
                err=True,
            )
            sys.exit(1)

    def get_repository_dsn(self, application_uuid):
        """
        Try to return the DSN of a remote repository for a given application_uuid.
        """
        response = self.get_project(application_uuid)
        repository_uuid = response.get("repository")

        # if the repository uuid is None it means that the repository is
        # hosted by divio and its dsn is well known
        if repository_uuid is None:
            return f"git@git.{get_divio_zone()}:{response['slug']}.git"

        try:
            request = api_requests.RepositoryRequest(
                self.session, url_kwargs={"repository_uuid": repository_uuid}
            )
            response = request()
            return response["dsn"]

        except IndexError:
            # happens when there is no remote repository configured
            return None

        raise DivioException("Could not get remote repository information.")

    def get_service_instance(
        self, instance_type, environment_uuid, prefix=None, limit_results=10
    ):
        if instance_type not in ["STORAGE", "DATABASE"]:
            raise ValueError(f"invalid type: {instance_type}")

        prefix = prefix or "DEFAULT"
        try:
            results, _ = json_response_request_paginate(
                api_requests.ListServiceInstancesRequest,
                self.session,
                url_kwargs={"environment_uuid": environment_uuid},
                limit_results=limit_results,
            )

            matches = [
                r
                for r in (results or {})
                if r["type"] == instance_type and r["prefix"] == prefix
            ]

            if len(matches) == 0:
                raise DivioException(
                    f"No service of type {instance_type} with prefix {prefix} "
                    f"found for environment {environment_uuid}."
                )

            if len(matches) == 1:
                return matches[0]

            raise DivioException(
                f"Multiple services instances found for type {instance_type} (prefix={prefix})",
            )

        except json.decoder.JSONDecodeError:
            raise DivioException(
                "Could not fetch service instances.",
            )

    def create_backup(
        self,
        environment_uuid: str,
        service_instance_uuid: str,
        notes: str | None = None,
        delete_at: datetime | None = None,
    ):
        data = {
            "environment": environment_uuid,
            "services": [service_instance_uuid],
            "trigger": "MANUAL",
        }

        if delete_at is not None:
            data["scheduled_for_deletion_at"] = delete_at.isoformat().replace(
                "+00:00",
                "Z",  # match django rest framework's formatting
            )
        if notes is not None:
            data["notes"] = notes

        return api_requests.CreateBackupRequest(self.session, data=data)()

    def get_backup(self, backup_uuid):
        return api_requests.GetBackupRequest(
            self.session,
            url_kwargs={"backup_uuid": backup_uuid},
        )()

    def get_service_instance_backup(self, backup_si_uuid):
        return api_requests.GetServiceInstanceBackupRequest(
            self.session,
            url_kwargs={"backup_si_uuid": backup_si_uuid},
        )()

    def create_backup_download(
        self, backup_uuid, backup_service_instance_uuid
    ):
        response = api_requests.CreateBackupDownloadRequest(
            self.session,
            data={
                "backup": backup_uuid,
                "service_instance_backups": [backup_service_instance_uuid],
                "trigger": "PULL",
            },
        )()

        backup_download_uuid = response.get("uuid")
        if not backup_download_uuid:
            raise DivioException("Could not create backup download.")

        try:
            results, _ = json_response_request_paginate(
                api_requests.ListBackupDownloadServiceInstancesRequest,
                self.session,
                params={"backup": backup_download_uuid},
                limit_results=10,
            )
            if results:
                backup_download_service_instance = results[0]
                return (
                    backup_download_uuid,
                    backup_download_service_instance["uuid"],
                )
            else:
                raise DivioException(
                    "Could not find service instance backup download "
                    f"for backup download {backup_download_uuid}."
                )

        except json.decoder.JSONDecodeError:
            raise DivioException(
                "Error while fetching service instance backups."
            )

    def get_backup_download_service_instance(
        self, backup_download_service_instance_uuid
    ):
        return api_requests.GetBackupDownloadServiceInstanceRequest(
            self.session,
            url_kwargs={
                "backup_download_si_uuid": backup_download_service_instance_uuid
            },
        )()

    def backup_upload_request(
        self,
        environment: str,
        service_intance_uuids: list[str],
        notes: str | None = None,
        delete_at: datetime | None = None,
    ):
        data = {
            "environment": environment,
            "services": service_intance_uuids,
        }

        if delete_at is not None:
            data["scheduled_for_deletion_at"] = delete_at.isoformat()
        if notes is not None:
            data["notes"] = notes

        return api_requests.CreateBackupUploadRequest(
            self.session, data=data
        )()

    def finish_backup_upload(self, finish_url):
        return requests.post(url=finish_url)

    def create_backup_restore(
        self, backup_uuid: str, si_backup_uuid: str, notes: str | None = None
    ):
        data = {
            "backup": backup_uuid,
            "service_instance_restores": [
                {"service_instance_backup": si_backup_uuid},
            ],
        }

        if notes is not None:
            data["notes"] = notes

        return api_requests.CreateBackupRestoreRequest(
            self.session, data=data
        )()

    def get_backup_restore(self, backup_restore_uuid: str):
        return api_requests.GetBackupRestoreRequest(
            self.session,
            url_kwargs={
                "backup_restore_uuid": backup_restore_uuid,
            },
        )()

    def validate_application_field(self, field, value):
        try:
            return api_requests.CreateApplicationRequest(
                self.session,
                data={
                    field: value,
                },
                proceed_on_4xx=True,
            )()
        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                (
                    "Error establishing connection while "
                    f"validating application field {field!r}."
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)

    def validate_repository_field(self, field, value):
        try:
            return api_requests.CreateRepositoryRequest(
                self.session,
                data={
                    field: value,
                },
                proceed_on_4xx=True,
            )()
        except (KeyError, json.decoder.JSONDecodeError):
            click.secho(
                (
                    "Error establishing connection while "
                    f"validating repository field {field!r}."
                ),
                fg="red",
                err=True,
            )
            sys.exit(1)
