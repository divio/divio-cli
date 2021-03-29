import json
import os
import re
import sys
from netrc import netrc
from time import sleep

import click
from dateutil.parser import isoparse
from six.moves.urllib_parse import urlparse
from tzlocal import get_localzone

from . import api_requests, messages, settings
from .config import Config
from .utils import json_dumps_unicode
from .localdev.utils import get_project_settings, get_project_home


ENDPOINT = "https://control.{host}"
DEFAULT_HOST = "divio.com"


def get_divio_host():
    try:
        project_specific_host = get_project_settings(get_project_home()).get("host", None)
    except click.ClickException:
        # Happens when there is no configuration file
        pass
    else:
        if project_specific_host:
            return project_specific_host
    return os.environ.get("DIVIO_HOST", DEFAULT_HOST) 


def get_endpoint(host=None):
    if not host:
        host = get_divio_host()
    if re.match("^https?://", host):
        endpoint = host
    else:
        endpoint = ENDPOINT.format(host=host)

    if host != DEFAULT_HOST:
        click.secho("Using custom endpoint {}\n".format(endpoint), fg="yellow")
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
    def __init__(self, endpoint, debug=False):
        self.debug = debug
        self.config = Config()
        self.endpoint = endpoint
        self.netrc = WritableNetRC()
        self.session = self.init_session()

    # Helpers
    def get_auth_header(self):
        host = urlparse(self.endpoint).hostname
        data = self.netrc.hosts.get(host)
        if data:
            return {"Authorization": "Token {}".format(data[2])}
        return {}

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
            greeting = u"{} {} ({})".format(first_name, last_name, email)
        elif first_name:
            greeting = u"{} ({})".format(first_name, email)
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

    def get_projects(self):
        request = api_requests.ProjectListRequest(self.session)
        return request()

    def ssh(self, website_id, stage):
        project_data = self.get_project(website_id)
        try:
            status = project_data["{}_status".format(stage)]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(stage),
                fg="red",
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
                click.secho("Error establishing ssh connection.", fg="red")
                sys.exit(1)

        else:
            click.secho(
                "SSH connection not available: environment '{}' not deployed yet.".format(
                    stage
                ),
                fg="yellow",
            )
            sys.exit(1)

    def show_log(self, website_id, stage, tail=False, utc=True):
        def print_log_data(data):
            for entry in data:
                dt = isoparse(entry["timestamp"])
                if not utc:
                    dt = dt.astimezone(get_localzone())
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
            status = project_data["{}_status".format(stage)]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(stage),
                fg="red",
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
                click.secho("Error retrieving logs.", fg="red")
                sys.exit(1)

        else:
            click.secho(
                "Logs not available: environment '{}' not deployed yet.".format(
                    stage
                ),
                fg="yellow",
            )
            sys.exit(1)

    def show_deploy_log(self, website_id, stage):
        project_data = self.get_project(website_id)
        # If we have tried to deploy before, there will be a log
        try:
            status = project_data["{}_status".format(stage)][
                "last_deployment"
            ]["status"]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(stage),
                fg="red",
            )
            sys.exit(1)
        if status:
            deploy_log = self.get_deploy_log(website_id, stage)
            task_id = "Deploy Log {}".format(deploy_log["task_id"])
            output = task_id + "\n" + deploy_log["output"]
            click.echo_via_pager(output)
        else:
            click.secho(
                "No {} environment deployed yet, no log available.".format(
                    stage
                ),
                fg="yellow",
            )

    def deploy_project_or_get_progress(self, website_id, stage):
        def fmt_progress(data):
            if not data:
                return "Connecting to remote"
            if isinstance(data, dict):
                return "{} ({})".format(
                    data.get("verbose_state", "..."),
                    data.get("heartbeat_ago_formatted", "?"),
                )
            return data

        response = self.deploy_project_progress(website_id, stage)
        if response["is_deploying"]:
            click.secho(
                "Already deploying {} environment, attaching to running "
                "deployment".format(stage),
                fg="yellow",
            )
        else:
            click.secho("Deploying {} environment".format(stage), fg="green")
            self.deploy_project(website_id, stage)
            sleep(1)
            response = self.deploy_project_progress(website_id, stage)
        try:
            with click.progressbar(
                length=100,
                show_percent=True,
                show_eta=False,
                item_show_func=fmt_progress,
            ) as bar:
                progress_percent = 0
                while response["is_deploying"]:
                    response = self.deploy_project_progress(website_id, stage)
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
                        "\nDeployment failed. Please run 'divio project deploy-log {}' "
                        "to get more information".format(stage)
                    )
                else:
                    bar.current_item = "Done"
                    bar.update(100)

        except KeyboardInterrupt:
            click.secho("Disconnected")

    def deploy_project_progress(self, website_id, stage):
        request = api_requests.DeployProjectProgressRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        data = request()
        try:
            return data[stage]
        except KeyError:
            click.secho(
                "Environment with the name '{}' does not exist.".format(stage),
                fg="red",
            )
            sys.exit(1)

    def deploy_project(self, website_id, stage):
        data = {"stage": stage}
        request = api_requests.DeployProjectRequest(
            self.session, url_kwargs={"website_id": website_id}, data=data
        )
        return request()

    def get_deploy_log(self, website_id, stage):
        request = api_requests.DeployLogRequest(
            self.session, url_kwargs={"website_id": website_id, "stage": stage}
        )
        return request()

    def get_project(self, website_id):
        request = api_requests.ProjectDetailRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        return request()

    def is_project_locked(self, website_id):
        request = api_requests.ProjectLockQueryRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        return request()

    def lock_project(self, website_id):
        request = api_requests.ProjectLockRequest(
            self.session, url_kwargs={"website_id": website_id}
        )
        return request()

    def unlock_project(self, website_id):
        request = api_requests.ProjectUnlockRequest(
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

    def get_website_slug_for_id(self, website_id):
        request = api_requests.IDToSlugRequest(
            self.session, url_kwargs={"website_id": website_id}
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

    def download_db_request(self, website_id, stage, prefix):
        request = api_requests.DownloadDBRequestRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": stage, "prefix": prefix},
        )
        return request()

    def download_db_progress(self, url):
        request = api_requests.DownloadDBProgressRequest(self.session, url=url)
        return request()

    def download_media_request(self, website_id, stage):
        request = api_requests.DownloadMediaRequestRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": stage},
        )
        return request()

    def download_media_progress(self, url):
        request = api_requests.DownloadMediaProgressRequest(
            self.session, url=url
        )
        return request()

    def upload_db(self, website_id, stage, archive_path, prefix):
        request = api_requests.UploadDBRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": stage, "prefix": prefix},
            files={"db_dump": open(archive_path, "rb")},
        )
        return request()

    def upload_db_progress(self, url):
        request = api_requests.UploadDBProgressRequest(self.session, url=url)
        return request()

    def upload_media(self, website_id, stage, archive_path, prefix="DEFAULT"):
        request = api_requests.UploadMediaFilesRequest(
            self.session,
            url_kwargs={"website_id": website_id},
            data={"stage": stage, "prefix": prefix},
            files={"media_files": open(archive_path, "rb")},
        )
        return request()

    def upload_media_progress(self, url):
        request = api_requests.UploadMediaFilesProgressRequest(
            self.session, url=url
        )
        return request()

    def get_environment_variables(self, website_id, stage, custom_only=True):
        if custom_only:
            Request = api_requests.GetCustomEnvironmentVariablesRequest
        else:
            Request = api_requests.GetEnvironmentVariablesRequest

        request = Request(
            self.session, url_kwargs={"website_id": website_id, "stage": stage}
        )
        return request()

    def set_custom_environment_variables(
        self, website_id, stage, set_vars, unset_vars
    ):
        current_vars = self.get_environment_variables(
            website_id, stage, custom_only=True
        )
        current_vars.update(set_vars)
        for var in unset_vars:
            current_vars.pop(var, None)
        request = api_requests.SetCustomEnvironmentVariablesRequest(
            self.session,
            url_kwargs={"website_id": website_id, "stage": stage},
            data={"vars": json_dumps_unicode(current_vars)},
        )
        return request()

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
