import functools
import json
import os
import sys
from functools import partial

import click
import sentry_sdk
import simple_logging_setup
from click_aliases import ClickAliasedGroup
from sentry_sdk.integrations.atexit import AtexitIntegration

import divio_cli

from . import localdev, messages, settings
from .check_system import check_requirements, check_requirements_human
from .cloud import CloudClient, get_endpoint
from .excepthook import DivioExcepthookIntegration, divio_shutdown
from .exceptions import (
    DivioException,
    EnvironmentDoesNotExist,
    ExitCode,
)
from .localdev.utils import (
    allow_remote_id_override,
    get_project_settings,
    migrate_project_settings,
)
from .upload.addon import upload_addon
from .upload.boilerplate import upload_boilerplate
from .utils import (
    Map,
    clean_table_cell,
    echo_environment_variables_as_txt,
    echo_large_content,
    get_cp_url,
    get_git_checked_branch,
    hr,
    launch_url,
    open_application_cloud_site,
    table,
)
from .validators.addon import validate_addon
from .validators.boilerplate import validate_boilerplate


try:
    import ipdb as pdb  # noqa: T100
except ImportError:
    import pdb  # noqa: T100

# Display the default value for options globally.
click.option = partial(click.option, show_default=True)


@click.group(
    cls=ClickAliasedGroup,
    context_settings={"help_option_names": ["--help", "-h"]},
)
@click.option(
    "-d",
    "--debug/--no-debug",
    default=False,
    help="Drop into the debugger if command execution raises an exception.",
)
@click.option(
    "-z",
    "--zone",
    default=None,
    help="Specify the Divio zone. Defaults to divio.com.",
)
@click.option(
    "-s",
    "--sudo",
    default=False,
    is_flag=True,
    help="Run as sudo?",
    hidden=True,
)
@click.option(
    "-v",
    "--verbose",
    count=True,
)
@click.pass_context
def cli(ctx, debug, zone, sudo, verbose):

    # setup logging
    log_level = "info"
    loggers = []

    if verbose > 0:
        log_level = "debug"

        loggers.extend(
            [
                "+root",
                "+http-request",
                "+http-response",
            ]
        )

    if verbose > 1:
        loggers.extend(
            [
                "+http-response-body",
            ]
        )

    if verbose > 2:
        loggers.clear()

    simple_logging_setup.setup(
        preset="cli",
        level=log_level,
        loggers=loggers,
    )

    # check version
    if sys.version_info < settings.MINIMAL_PYTHON_VERSION:
        current_version_string = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        minimal_version_string = ".".join(
            str(i) for i in settings.MINIMAL_PYTHON_VERSION
        )

        click.secho(
            f"deprecation warning: Python {minimal_version_string} is required (Python {current_version_string} is running)",
            fg="yellow",
        )

    if sudo:
        click.secho("Running as sudo", fg="yellow")

    if zone:
        os.environ["DIVIO_ZONE"] = zone

    ctx.obj = Map()
    ctx.obj.client = CloudClient(
        get_endpoint(zone=zone), debug=debug, sudo=sudo
    )
    ctx.obj.zone = zone

    if debug:

        def exception_handler(type, value, traceback):
            click.secho(
                "\nAn exception occurred while executing the requested "
                "command:",
                fg="red",
                err=True,
            )
            hr(
                fg="red",
                err=True,
            )
            sys.__excepthook__(type, value, traceback)
            click.secho(
                "\nStarting interactive debugging session:", fg="red", err=True
            )
            hr(
                fg="red",
                err=True,
            )
            pdb.post_mortem(traceback)

        sys.excepthook = exception_handler
    else:
        sentry_sdk.init(
            ctx.obj.client.config.get_sentry_dsn(),
            traces_sample_rate=0,
            release=divio_cli.__version__,
            server_name="client",
            integrations=[
                DivioExcepthookIntegration(),
                AtexitIntegration(callback=divio_shutdown),
            ],
        )

    try:
        is_version_command = sys.argv[1] == "version"
    except IndexError:
        is_version_command = False

    # migrate project_settings if needed
    migrate_project_settings(client=ctx.obj.client)

    # skip if 'divio version' is run
    if not is_version_command:
        # check for newer versions
        update_info = ctx.obj.client.config.check_for_updates()
        if update_info["update_available"]:
            click.secho(
                "New version {} is available. Type `divio version` to "
                "show information about upgrading.".format(
                    update_info["remote"]
                ),
                fg="yellow",
                err=True,
            )


def login_token_helper(ctx, value):
    if not value:
        url = ctx.obj.client.get_access_token_url()
        click.secho(f"Your browser has been opened to visit: {url}")
        launch_url(url)
        value = click.prompt(
            "Please copy the access token and paste it here. (your input is not displayed)",
            hide_input=True,
        )

    # Detect pasting shortcut malfunction (Windows users)
    # When this shortcut is disabled then the character \x16
    # (which will appear as ^V) is generated by the terminal when trying to use it.
    if "".join(set(value)) == "\x16":
        click.secho(
            "\nThe access token provided indicates a copy/paste malfunction.\nRead more here: https://r.divio.com/divio-login-windows-users.",
            fg="yellow",
        )
    return value


@cli.command()
@click.argument("token", required=False)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Check for current login status.",
)
@click.pass_context
def login(ctx, token, check):
    """Authorise your machine with the Divio Control Panel."""
    success = True
    if check:
        success, msg = ctx.obj.client.check_login_status()
    else:
        token = login_token_helper(ctx, token)
        msg = ctx.obj.client.login(token)

    click.echo(msg)
    sys.exit(ExitCode.SUCCESS if success else ExitCode.GENERIC_ERROR)


@cli.command()
@click.option(
    "--non-interactive",
    is_flag=True,
    default=False,
    help="Skip confirmation",
)
@click.pass_context
def logout(ctx, non_interactive):
    """Log off from Divio Control Panel"""
    sys.exit(ctx.obj["client"].logout(interactive=not non_interactive))


@cli.group(name="services")
def services():
    """Pull db or files from the Divio cloud environment."""


@services.command(name="list")
@click.option(
    "-r",
    "--region",
    required=True,
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
def list_services(obj, region, as_json):
    """List all available services for a regions."""
    api_response = obj.client.get_services(region_uuid=region)

    if as_json:
        click.echo(json.dumps(api_response, indent=2, sort_keys=True))
        return
    if not api_response["results"]:
        click.echo("No services found.")
        return

    headers = ["UUID", "Name", "Type", "Description"]
    data = [
        [
            entry["uuid"],
            entry["name"],
            entry["type"],
            entry["description"],
        ]
        for entry in api_response["results"]
    ]
    output = table(data, headers, tablefmt="grid", maxcolwidths=30)

    echo_large_content(output, ctx=obj)


@cli.group(cls=ClickAliasedGroup, aliases=["project"])
def app():
    """Manage your application"""


@app.command(name="list")
@click.option(
    "-g",
    "--grouped",
    is_flag=True,
    default=False,
    help="Group by organisation.",
)
@click.option(
    "-p/-P",
    "--pager/--no-pager",
    default=False,
    is_flag=True,
    help="Choose whether to display content via pager.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
def application_list(obj, grouped, pager, as_json):
    """List all your applications."""
    obj.pager = pager
    api_response = obj.client.get_applications()

    if as_json:
        click.echo(json.dumps(api_response, indent=2, sort_keys=True))
        return

    header = ["ID", "Slug", "Name", "Organisation"]

    data = {}
    for application in api_response["results"]:
        org_name = obj.client.get_organisation(application["organisation"])[
            "name"
        ]
        if not data.get(org_name):
            data[org_name] = []
        data[org_name].append(
            (application["uuid"], application["slug"], application["name"])
        )

    def sort_applications(items):
        return sorted(items, key=lambda x: x[0].lower())

    # print via pager
    if grouped:
        output_items = []
        for organisation in data:
            output_items.append(
                "{title}\n{line}\n\n{table}\n\n".format(
                    title=organisation,
                    line="=" * len(organisation),
                    table=table(
                        sort_applications(data[organisation]), header[:3]
                    ),
                )
            )
        output = os.linesep.join(output_items).rstrip(os.linesep)
    else:
        # add org name to all applications
        applications = [
            (*each, organisation)
            for organisation in data
            for each in data[organisation]
        ]
        output = table(sort_applications(applications), header)

    echo_large_content(output, ctx=obj)


@app.command(name="deploy")
@click.argument("environment", default="test")
@click.pass_obj
@allow_remote_id_override
def application_deploy(obj, remote_id, environment):
    """Deploy application."""
    obj.client.deploy_application_or_get_progress(remote_id, environment)


@app.command(name="deploy-log")
@click.argument("environment", default="test")
@click.pass_obj
@allow_remote_id_override
def application_deploy_log(obj, remote_id, environment):
    """View last deployment log."""
    deploy_log = obj.client.get_deploy_log(remote_id, environment)
    if deploy_log:
        echo_large_content(deploy_log, ctx=obj)
    else:
        click.secho(
            "No logs available.",
            fg="yellow",
        )


@app.command(name="logs")
@click.argument("environment", default="test")
@click.option(
    "--tail", "tail", default=False, is_flag=True, help="Tail the output."
)
@click.option(
    "--utc", "utc", default=False, is_flag=True, help="Show times in UTC/"
)
@click.pass_obj
@allow_remote_id_override
def application_logs(obj, remote_id, environment, tail, utc):
    """View logs."""
    obj.client.show_log(remote_id, environment, tail, utc)


@app.command(name="ssh")
@click.argument("environment", default="test")
@click.pass_obj
@allow_remote_id_override
def application_ssh(obj, remote_id, environment):
    """Establish SSH connection."""
    obj.client.ssh(remote_id, environment)


@app.command(name="configure")
@click.pass_obj
def configure(obj):
    """Associate a local application with a Divio cloud applications."""
    localdev.configure(client=obj.client, zone=obj.zone)


@app.command(name="dashboard")
@click.pass_obj
@allow_remote_id_override
def application_dashboard(obj, remote_id):
    """Open the application dashboard on the Divio Control Panel."""
    zone = get_project_settings(silent=True)["zone"]
    launch_url(
        get_cp_url(
            client=obj.client, application_id=remote_id, zone=obj.zone or zone
        )
    )


@app.command(name="up", aliases=["start"])
def application_up():
    """Start the local application (equivalent to: docker-compose up)."""
    localdev.start_application()


@app.command(name="down", aliases=["stop"])
def application_down():
    """Stop the local application."""
    localdev.stop_application()


@app.command(name="open")
@click.argument("environment", default="")
@click.pass_obj
@allow_remote_id_override
def application_open(obj, remote_id, environment):
    """Open local or cloud applications in a browser."""
    if environment:
        open_application_cloud_site(
            obj.client, application_id=remote_id, environment=environment
        )
    else:
        localdev.open_application()


@app.command(name="update")
@click.option(
    "--strict",
    "strict",
    default=False,
    is_flag=True,
    help="A strict update will fail on a warning.",
)
@click.pass_obj
def application_update(obj, strict):
    """Update the local application with new code changes, then build it.

    Runs:

    git pull
    docker-compose pull
    docker-compose build
    docker-compose run web start migrate"""

    localdev.update_local_application(
        get_git_checked_branch(), client=obj.client, strict=strict
    )


# Deployments group.
@app.group()
@click.option(
    "-p/-P",
    "--pager/--no-pager",
    default=False,
    is_flag=True,
    help="Choose whether to display content via pager.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
def deployments(obj, pager, as_json):
    """Retrieve deployments."""

    obj.pager = pager
    obj.as_json = as_json

    # Deployments in table format display less content than in
    # json format. Here are the desired columns to be displayed.
    obj.table_format_columns = [
        "uuid",
        "author",
        "started_at",
        "ended_at",
        "status",
        "success",
    ]


@deployments.command(name="list")
@click.option(
    "-s",
    "--stage",
    "-e",
    "--environment",
    "environment",
    default="test",
    type=str,
    help="Select an environment (by name) from which deployments will be retrieved.",
)
@click.option(
    "--all-envs",
    "--all-environments",
    "all_environments",
    default=False,
    is_flag=True,
    help="Retrieve deployments from all available environments.",
)
@click.option(
    "--limit",
    "--limit-results",
    "limit_results",
    type=int,
    help="The maximum number of results that can be retrieved.",
)
@click.pass_obj
@allow_remote_id_override
def list_deployments(
    obj, remote_id, environment, all_environments, limit_results
):
    """
    Retrieve deployments from an environment or
    deployments across all environments of an application.
    """

    results, messages = obj.client.list_deployments(
        application_uuid=remote_id,
        environment=environment,
        all_environments=all_environments,
        limit_results=limit_results,
    )

    if obj.as_json:
        json_content = json.dumps(results, indent=2)
        echo_large_content(json_content, ctx=obj)
    else:
        content = ""
        for result in results:
            content_table_title = f"Environment: {result['environment']} ({result['environment_uuid']})"
            columns = obj.table_format_columns
            rows = [
                [row[key] for key in columns] for row in result["deployments"]
            ]
            content_table = table(rows, columns, tablefmt="grid")
            content += f"{content_table_title}\n{content_table}\n\n"
        echo_large_content(content.strip("\n"), ctx=obj)

    if messages:
        click.echo()
        for msg in messages:
            click.secho(msg, fg="yellow")


@deployments.command(name="get")
@click.argument("deployment_uuid")
@click.pass_obj
@allow_remote_id_override
def get_deployment(obj, remote_id, deployment_uuid):
    """
    Retrieve a deployment (by uuid).
    """

    response = obj.client.get_deployment(remote_id, deployment_uuid)
    deployment = response["deployment"]
    if obj.as_json:
        json_content = json.dumps([response], indent=2)
        echo_large_content(json_content, ctx=obj)
    else:
        content_table_title = f"Environment: {response['environment']} ({response['environment_uuid']})"
        deployment["environment_variables"] = ", ".join(
            deployment["environment_variables"]
        )
        # Flipped table.
        columns = [*obj.table_format_columns, "environment_variables"]
        rows = [[key, deployment[key] or ""] for key in columns]
        content_table = table(
            rows, headers=(), tablefmt="grid", maxcolwidths=50
        )
        content = f"{content_table_title}\n{content_table}"
        echo_large_content(content, ctx=obj)


@deployments.command(name="get-var")
@click.argument("deployment_uuid")
@click.argument("variable_name")
@click.pass_obj
@allow_remote_id_override
def get_deployment_environment_variable(
    obj, remote_id, deployment_uuid, variable_name
):
    """
    Retrieve an environment variable (by name) from a deployment (by uuid).
    """

    response = obj.client.get_deployment_with_environment_variables(
        remote_id,
        deployment_uuid,
        variable_name,
    )
    deployment = response["deployment"]
    env_var = {
        "name": variable_name,
        "value": deployment["environment_variables"].get(variable_name),
        "environment": response["environment"],
        "environment_uuid": response["environment_uuid"],
    }
    if obj.as_json:
        json_content = json.dumps([env_var], indent=2)
        echo_large_content(json_content, ctx=obj)
    else:
        content_table_title = f"Environment: {response['environment']} ({response['environment_uuid']})"
        columns = ["name", "value"]
        # Flipped table.
        rows = [[key, clean_table_cell(env_var, key)] for key in columns]
        content_table = table(
            rows, headers=(), tablefmt="grid", maxcolwidths=50
        )
        content = f"{content_table_title}\n{content_table}"
        echo_large_content(content, ctx=obj)


# Environment variables group.
@app.group(aliases=["env-vars"])
@click.option(
    "-p/-P",
    "--pager/--no-pager",
    default=False,
    is_flag=True,
    help="Choose whether to display content via pager.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.option(
    "--txt",
    "as_txt",
    is_flag=True,
    default=False,
    help="Choose whether to display content in a simple txt-like format (names and values only).",
)
@click.pass_obj
def environment_variables(obj, pager, as_json, as_txt):
    """Retrieve environment variables."""

    obj.pager = pager
    obj.as_json = as_json
    obj.as_txt = as_txt

    # Environment variables in table format display less content than in
    # json format. Here are the desired columns to be displayed.
    obj.table_format_columns = ["name", "value", "is_sensitive"]


@environment_variables.command("list")
@click.option(
    "-s",
    "--stage",
    "-e",
    "--environment",
    "environment",
    default="test",
    type=str,
    help="Select an environment (by name) from which environment variables will be retrieved.",
)
@click.option(
    "--all-envs",
    "--all-environments",
    "all_environments",
    default=False,
    is_flag=True,
    help="Retrieve environment variables from all available environments.",
)
@click.option(
    "--limit",
    "--limit-results",
    "limit_results",
    type=int,
    help="The maximum number of results that can be retrieved.",
)
@click.pass_obj
@allow_remote_id_override
def list_environment_variables(
    obj, remote_id, environment, all_environments, limit_results
):
    """
    Retrieve environment variables from an environment
    or environment variables across all environments of an application.
    """

    results, messages = obj.client.list_environment_variables(
        application_uuid=remote_id,
        environment=environment,
        all_environments=all_environments,
        limit_results=limit_results,
    )
    # No need to include the environment uuid in each variable
    # as it is provided anyway for both json and table format.
    for result in results:
        for env_var in result["environment_variables"]:
            env_var.pop("environment")

    if obj.as_json:
        json_content = json.dumps(results, indent=2)
        echo_large_content(json_content, ctx=obj)
    elif obj.as_txt:
        echo_environment_variables_as_txt(
            results, obj, all_environments, environment
        )
    else:
        content = ""
        for result in results:
            content_table_title = f"Environment: {result['environment']} ({result['environment_uuid']})"
            columns = obj.table_format_columns
            rows = [
                [clean_table_cell(row, key) for key in columns]
                for row in result["environment_variables"]
            ]
            content_table = table(
                rows, columns, tablefmt="grid", maxcolwidths=50
            )
            content += f"{content_table_title}\n{content_table}\n\n"

        echo_large_content(content.strip("\n"), ctx=obj)

    if messages:
        click.echo()
        for msg in messages:
            click.secho(msg, fg="yellow")


@environment_variables.command("get")
@click.option(
    "-s",
    "--stage",
    "-e",
    "--environment",
    "environment",
    default="test",
    type=str,
    help="Select an environment (by name) from which the environment variable will be retrieved.",
)
@click.option(
    "--all-envs",
    "--all-environments",
    "all_environments",
    default=False,
    is_flag=True,
    help="Retrieve an environment variable across all environments.",
)
@click.option(
    "--limit",
    "--limit-results",
    "limit_results",
    type=int,
    help="The maximum number of results that can be retrieved.",
)
@click.argument("variable_name")
@click.pass_obj
@allow_remote_id_override
def get_environment_variable(
    obj, remote_id, variable_name, environment, all_environments, limit_results
):
    """
    Retrieve an environment variable (by name) from an environment
    or any occurrence of it across all environments of an application.
    """

    results, messages = obj.client.list_environment_variables(
        application_uuid=remote_id,
        environment=environment,
        all_environments=all_environments,
        limit_results=limit_results,
        variable_name=variable_name,
    )

    if results:
        if obj.as_json:
            echo_large_content(json.dumps(results, indent=2), ctx=obj)
        elif obj.as_txt:
            echo_environment_variables_as_txt(
                results, obj, all_environments, environment, variable_name
            )
        else:
            content = ""
            for result in results:
                # Each environment will only include one environment variable
                # because of the name filter applied previously in the request.
                env_var = result["environment_variables"][0]
                content_table_title = f"Environment: {result['environment']} ({result['environment_uuid']})"
                columns = obj.table_format_columns
                row = [[clean_table_cell(env_var, key) for key in columns]]

                content_table = table(
                    row, columns, tablefmt="grid", maxcolwidths=50
                )
                content += f"{content_table_title}\n{content_table}\n\n"
            echo_large_content(content.strip("\n"), ctx=obj)
    else:
        click.secho(
            f"Could not find an environment variable named {variable_name!r} in any of the available environments."
            if all_environments
            else f"Could not find an environment variable named {variable_name!r} for {environment!r} environment.",
            fg="yellow",
        )

    if messages:
        click.echo()
        for msg in messages:
            click.secho(msg, fg="yellow")


@app.command(name="status")
def app_status():
    """Show local application status."""
    localdev.show_application_status()


@app.command(name="setup")
@click.argument("slug")
@click.option(
    "-s",
    "--stage",
    "-e",
    "--environment",
    "environment",
    default="test",
    help="Specify environment from which media and content data will be pulled.",
)
@click.option(
    "-p",
    "--path",
    default=".",
    help="Install application in path.",
    type=click.Path(writable=True, readable=True),
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite the application directory if it already exists.",
)
@click.option(
    "--skip-doctor",
    is_flag=True,
    default=False,
    help="Skip system test before setting up the application.",
)
@click.pass_obj
def application_setup(obj, slug, environment, path, overwrite, skip_doctor):
    """Set up a development environment for a Divio application."""
    if not skip_doctor and not check_requirements_human(
        config=obj.client.config, silent=True
    ):
        raise DivioException(
            "There was a problem while checking your system. Please run "
            "'divio doctor'."
        )

    localdev.create_workspace(
        obj.client, slug, environment, path, overwrite, obj.zone
    )


@app.group(name="service-instances")
def service_instances():
    """Commands for service instances like a database or storage."""


@service_instances.command(name="list")
@click.argument("environment", default="test")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
@allow_remote_id_override
def list_service_instances(obj, remote_id, environment, as_json):
    """List the services instances of an application"""
    try:
        environment_uuid = obj.client.get_environment(remote_id, environment)[
            "uuid"
        ]

    except KeyError:
        raise EnvironmentDoesNotExist(environment)

    api_response = obj.client.get_service_instances(
        environment_uuid=environment_uuid,
    )

    if as_json:
        click.echo(json.dumps(api_response, indent=2, sort_keys=True))
        return
    if not api_response["results"]:
        click.echo("No service instances found.")
        return

    headers = [
        "UUID",
        "Prefix",
        "Type",
        "Service  Status",
        "Region",
        "Service",
    ]
    data = [
        [
            entry["uuid"],
            entry["prefix"],
            entry["type"],
            entry["service_status"],
            entry["region"],
            entry["service"],
        ]
        for entry in api_response["results"]
    ]
    output = table(data, headers, tablefmt="grid", maxcolwidths=30)

    echo_large_content(output, ctx=obj)


@service_instances.command(name="add")
@click.argument("environment", default="test")
@click.option(
    "-p",
    "--prefix",
    required=True,
)
@click.option(
    "-r",
    "--region",
    required=True,
)
@click.option(
    "-s",
    "--service",
    required=True,
)
@click.pass_obj
@allow_remote_id_override
def add_service_instances(
    obj, remote_id, environment, prefix, region, service
):
    """Adding a new service instance like a database to an application."""
    project_data = obj.client.get_project(remote_id)
    try:
        status = project_data[f"{environment}_status"]
    except KeyError:
        raise EnvironmentDoesNotExist(environment)

    obj.client.add_service_instances(
        environment_uuid=status["uuid"],
        prefix=prefix,
        region_uuid=region,
        service_uuid=service,
    )


@app.group(name="pull")
def application_pull():
    """Pull db or files from the Divio cloud environment."""


def common_pull_options(f):
    @click.option(
        "--keep-tempfile",
        is_flag=True,
        default=False,
        help="Keep the temporary file with the data.",
    )
    @click.option(
        "--service-instance-backup",
        "backup_si_uuid",
        type=str,
        default=None,
        help="The UUID of a service instance backup to restore.",
    )
    @click.argument("environment", default="test")
    @click.argument("prefix", default=localdev.DEFAULT_SERVICE_PREFIX)
    @click.pass_obj
    @allow_remote_id_override
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        if "prefix" in kwargs:
            # prefixes are always in capital letters
            kwargs["prefix"] = kwargs["prefix"].upper()
        return f(*args, **kwargs)

    return wrapper_common_options


@application_pull.command(name="db")
@common_pull_options
def pull_db(
    obj, remote_id, environment, prefix, keep_tempfile, backup_si_uuid
):
    """
    Pull database the Divio cloud environment.
    """
    from .localdev import utils

    application_home = utils.get_application_home()
    db_type = utils.get_db_type(prefix, path=application_home)
    dump_path = os.path.join(application_home, settings.DIVIO_DUMP_FOLDER)

    localdev.ImportRemoteDatabase(
        client=obj.client,
        environment=environment,
        prefix=prefix,
        application_uuid=remote_id,
        db_type=db_type,
        dump_path=dump_path,
        backup_si_uuid=backup_si_uuid,
        keep_tempfile=keep_tempfile,
    )()


@application_pull.command(name="media")
@common_pull_options
def pull_media(
    obj, remote_id, environment, prefix, keep_tempfile, backup_si_uuid
):
    """
    Pull media files from the Divio cloud environment.
    """
    localdev.pull_media(
        obj.client,
        environment=environment,
        prefix=prefix,
        application_uuid=remote_id,
        keep_tempfile=keep_tempfile,
        backup_si_uuid=backup_si_uuid,
    )


@app.group(name="push")
def application_push():
    """Push db or media files to the Divio cloud environment."""


def common_push_options(f):
    @click.argument("environment", default="test")
    @click.option(
        "--noinput",
        is_flag=True,
        default=False,
        help="Don't ask for confirmation.",
    )
    @click.option(
        "--keep-tempfile",
        is_flag=True,
        default=False,
        help="Keep the temporary file with the data.",
    )
    @click.argument("prefix", default=localdev.DEFAULT_SERVICE_PREFIX)
    @click.pass_obj
    @allow_remote_id_override
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        if "prefix" in kwargs:
            # prefixes are always in capital letters
            kwargs["prefix"] = kwargs["prefix"].upper()
        return f(*args, **kwargs)

    return wrapper_common_options


@application_push.command(name="db")
@common_push_options
@click.option(
    "-d",
    "--dumpfile",
    default=None,
    type=click.Path(exists=True),
    help="Specify a dumped database file to upload.",
)
def push_db(
    obj, remote_id, prefix, environment, dumpfile, noinput, keep_tempfile
):
    """
    Push database to the Divio cloud environment.
    """
    if not noinput:
        click.secho(
            messages.PUSH_DB_WARNING.format(environment=environment),
            fg="red",
        )
        if not click.confirm("\nAre you sure you want to continue?"):
            return

    localdev.push_db(
        client=obj.client,
        environment=environment,
        application_uuid=remote_id,
        prefix=prefix,
        local_file=dumpfile,
        keep_tempfile=keep_tempfile,
    )


@application_push.command(name="media")
@common_push_options
def push_media(obj, remote_id, prefix, environment, noinput, keep_tempfile):
    """
    Push media storage to the Divio cloud environment.
    """

    if not noinput:
        click.secho(
            messages.PUSH_MEDIA_WARNING.format(environment=environment),
            fg="red",
        )
        if not click.confirm("\nAre you sure you want to continue?"):
            return

    localdev.push_media(
        client=obj.client,
        environment=environment,
        application_uuid=remote_id,
        prefix=prefix,
        keep_tempfile=keep_tempfile,
    )


@app.group(name="import")
def application_import():
    """Import local database dump."""


@application_import.command(name="db")
@click.argument("prefix", default=localdev.DEFAULT_SERVICE_PREFIX)
@click.argument(
    "dump-path",
    default=localdev.DEFAULT_DUMP_FILENAME,
    type=click.Path(exists=True),
)
@click.pass_obj
def import_db(obj, dump_path, prefix):
    """
    Load a database dump into your local database.
    """
    from .localdev import utils

    application_home = utils.get_application_home()
    db_type = utils.get_db_type(prefix, path=application_home)
    localdev.ImportLocalDatabase(
        client=obj.client,
        custom_dump_path=dump_path,
        prefix=prefix,
        db_type=db_type,
    )()


@app.group(name="export")
def application_export():
    """Export local database dump."""


@application_export.command(name="db")
@click.argument("prefix", default=localdev.DEFAULT_SERVICE_PREFIX)
def export_db(prefix):
    """
    Export a dump of your local database
    """
    localdev.export_db(prefix=prefix)


@app.command(name="develop")
@click.argument("package")
@click.option(
    "--no-rebuild",
    is_flag=True,
    default=False,
    help="Do not rebuild docker container automatically.",
)
def application_develop(package, no_rebuild):
    """Add a package 'package' to your local application environment."""
    localdev.develop_package(package, no_rebuild)


@cli.group()
@click.option("-p", "--path", default=".", help="Addon directory")
@click.pass_obj
def addon(obj, path):
    """Validate and upload addons packages to the Divio cloud."""


@addon.command(name="validate")
@click.pass_context
def addon_validate(ctx):
    """Validate addon configuration."""
    validate_addon(ctx.parent.params["path"])
    click.echo("Addon is valid!")


@addon.command(name="upload")
@click.pass_context
def addon_upload(ctx):
    """Upload addon to the Divio Control Panel."""
    click.echo(upload_addon(ctx.obj.client, ctx.parent.params["path"]))


@addon.command(name="register")
@click.argument("verbose_name")
@click.argument("package_name")
@click.option(
    "-o",
    "--organisation",
    help="Register an addon for an organisation.",
    type=int,
)
@click.pass_context
def addon_register(ctx, package_name, verbose_name, organisation):
    """Register your addon on the Divio Control Panel\n
    - Verbose Name:        Name of the Addon as it appears in the Marketplace
    - Package Name:        System wide unique Python package name
    """
    ret = ctx.obj.client.register_addon(
        package_name, verbose_name, organisation
    )
    click.echo(ret)


@cli.group()
@click.option("-p", "--path", default=".", help="Boilerplate directory")
@click.pass_obj
def boilerplate(obj, path):
    """Validate and upload boilerplate packages to the Divio cloud."""


@boilerplate.command(name="validate")
@click.pass_context
def boilerplate_validate(ctx):
    """Validate boilerplate configuration."""
    validate_boilerplate(ctx.parent.params["path"])
    click.echo("Boilerplate is valid.")


@boilerplate.command(name="upload")
@click.option(
    "--noinput",
    is_flag=True,
    default=False,
    help="Don't ask for confirmation.",
)
@click.pass_context
def boilerplate_upload(ctx, noinput):
    """Upload boilerplate to the Divio Control Panel."""
    click.echo(
        upload_boilerplate(ctx.obj.client, ctx.parent.params["path"], noinput)
    )


@cli.command()
@click.option(
    "-s",
    "--skip-check",
    is_flag=True,
    default=False,
    help="Don't check PyPI for newer version.",
)
@click.option("-m", "--machine-readable", is_flag=True, default=False)
@click.pass_obj
def version(obj, skip_check, machine_readable):
    """Show version info."""
    if skip_check:
        from . import __version__

        update_info = {"current": __version__}
    else:
        update_info = obj.client.config.check_for_updates(force=True)

    update_info["location"] = os.path.dirname(os.path.realpath(sys.executable))

    if machine_readable:
        click.echo(json.dumps(update_info))
    else:
        click.echo(
            "divio-cli {} from {}\n".format(
                update_info["current"], update_info["location"]
            )
        )

        if not skip_check:
            if update_info["update_available"]:
                click.secho(
                    "New version {version} is available. Upgrade options:\n\n"
                    " - Using pip\n"
                    "   pip install --upgrade divio-cli\n\n"
                    " - Download the latest release from GitHub\n"
                    "   https://github.com/divio/divio-cli/releases".format(
                        version=update_info["remote"]
                    ),
                    fg="yellow",
                )
            elif update_info["pypi_error"]:
                click.secho(
                    "There was an error while trying to check for the latest "
                    "version on pypi.python.org:\n"
                    "{}".format(update_info["pypi_error"]),
                    fg="red",
                    err=True,
                )
            else:
                click.echo("You have the latest version of divio-cli.")


@cli.command()
@click.option("-m", "--machine-readable", is_flag=True, default=False)
@click.option("-c", "--checks", default=None)
@click.pass_obj
def doctor(obj, machine_readable, checks):
    """
    Check that your system meets the development requirements.

    To disable checks selectively in case of false positives, see
    https://docs.divio.com/en/latest/reference/divio-cli/#using-skip-doctor-checks
    """

    if checks:
        checks = checks.split(",")

    if machine_readable:
        errors = {
            check: error
            for check, check_name, error in check_requirements(
                obj.client.config, checks
            )
        }
        exitcode = 1 if any(errors.values()) else 0
        click.echo(json.dumps(errors), nl=False)
    else:
        click.echo("Verifying your system setup...")
        exitcode = (
            ExitCode.SUCCESS
            if check_requirements_human(obj.client.config, checks)
            else ExitCode.GENERIC_ERROR
        )

    sys.exit(exitcode)


@cli.group(cls=ClickAliasedGroup)
def organisations():
    "Manage your organisations"


@organisations.command(name="list")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
def list_organisations(obj, as_json):
    "List your organisations"
    api_response = obj.client.get_organisations()
    if as_json:
        click.echo(json.dumps(api_response, indent=2, sort_keys=True))
        return

    headers = [
        "UUID",
        "Name",
        "Created at",
    ]
    data = [
        [
            entry["uuid"],
            entry["name"],
            entry["created_at"],
        ]
        for entry in api_response["results"]
    ]
    output = table(data, headers, tablefmt="grid", maxcolwidths=50)

    echo_large_content(output, ctx=obj)


@cli.group(cls=ClickAliasedGroup)
def regions():
    """Manage regions"""


@regions.command(name="list")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Choose whether to display content in json format.",
)
@click.pass_obj
def list_regions(obj, as_json):
    """List all available regions"""
    api_response = obj.client.get_regions()
    if as_json:
        click.echo(json.dumps(api_response, indent=2, sort_keys=True))
        return

    headers = [
        "UUID",
        "Name",
    ]
    data = [
        [
            entry["uuid"],
            entry["name"],
        ]
        for entry in api_response["results"]
    ]
    output = table(data, headers, tablefmt="grid", maxcolwidths=50)

    echo_large_content(output, ctx=obj)
