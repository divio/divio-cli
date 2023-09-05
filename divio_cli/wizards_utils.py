from rich import box
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.json import JSON
import json

console = Console()

APP_WIZARD_MESSAGES = {
    # Welcome
    "welcome_message": (
        "Welcome to the application creation wizard where you'll be "
        "guided through the process of creating a new Divio application. "
        "You'll be now prompted to enter the required information. "
    ),
    # Name
    "enter_name": "Enter the name of your application",
    "name_missing": (
        "Error: Missing option '-n' / '--name'. "
        "Required in non-interactive mode."
    ),
    # Slug
    "enter_slug": "Enter the slug of your application",
    "slug_missing": (
        "Error: Missing option '-s' / '--slug'. "
        "Required in non-interactive mode."
    ),
    # Organisation
    "select_organisation": "Select an organisation for your application",
    "organisation_missing": (
        "Error: Missing option '-o' / '--organisation'. "
        "Required in non-interactive mode."
    ),
    "invalid_organisation": "ERROR: Invalid organization.",
    # Plan group
    "select_plan_group": "Select a plan for your application",
    "plan_group_missing": (
        "Error: Missing option '-p' / '--plan-group'. "
        "Required in non-interactive mode."
    ),
    "invalid_plan_group": "ERROR: Invalid plan.",
    # Region
    "select_region": "Select a region for your application",
    "region_missing": (
        "Error: Missing option '-r' / '--region'. "
        "Required in non-interactive mode."
    ),
    "invalid_region": "ERROR: Invalid region.",
    # Template
    "create_template": "Want to add a project template to your application?",
    "enter_template": "Enter the URL of your project template",
    "invalid_template_url": "ERROR: Invalid project template URL.",
    # Release commands
    "create_release_commands": "Want to create release commands for your application?",
    "enter_release_command_label": "Enter the label of your release command",
    "enter_release_command": "Enter your release command",
    "add_another_release_command": "Want to add another release command?",
    # Custom repository
    "connect_repository": "Want to connect a custom repository to your application?",
    "enter_repository_url": "Enter the URL of your custom repository",
    "enter_repository_branch_name": "Enter the name of your target branch",
    "select_repository_ssh_key_type": "Select the type of your deploy key",
    "create_deploy_key": (
        "Please register this ssh key with your repository provider. "
        "Otherwise, the repository verification will fail. Ready to continue?"
    ),
    "repository_verification_timeout": "Repository verification timed out.",
    "confirm_app_creation": "Confirm application creation to proceed.",
    # Deploy
    "deployment_triggered": "Deployment of test environment triggered.",
}

AVAILABLE_REPOSITORY_SSH_KEY_TYPES = [
    "ED25519",
    "ECDSA",
    "RSA",
]

def create_app_release_commands_summary(release_commands, as_json=False):
    """Return a rich table of release commands."""

    if not release_commands:
        return None

    if as_json:
        return JSON(json.dumps(release_commands))
    else:
        table = Table(
            box=box.MINIMAL, 
            show_lines=True,
        )
        table.add_column("Label", style="magenta")
        table.add_column("Command", style="cyan")
        for rc in release_commands:
            table.add_row(
                rc["label"],
                rc["command"],
            )

        return table


def log_app_details_summary(data, as_json=False):
    """Return a table of application details."""
    app_data = data["app"]
    app_meta = data["meta"]

    if as_json:
        app_details = {
            "name": app_data["name"],
            "slug": app_data["slug"],
            "organisation": {
                "name": app_meta["organisation_name"],
                "uuid": app_data["organisation"],
            },
            "plan_group": {
                "name": app_meta["plan_group_name"],
                "uuid": app_data["plan_group"],
            },
            "region": {
                "name": app_meta["region_name"],
                "uuid": app_data["region"],
            },
            "project_template": app_data["project_template"],
            "release_commands": app_data["release_commands"],
            "repository": {
                "url": app_meta["repository_url"],
                "branch": app_data["branch"],
                "uuid": app_data["repository"],
            } if app_data.get("repository") else {},
            "deploy": app_meta["deploy"],
        }
        
        app_details = JSON(json.dumps(app_details))
    else:
        release_commands_summary = create_app_release_commands_summary(
            app_data["release_commands"]
        ) or "—"

        app_details = Group(
            Panel(app_data["name"], title="Name"),
            Panel(app_data["slug"], title="Slug"),
            Panel(
                (
                    f"[magenta]Name[/magenta]: {app_meta['organisation_name']}\n"
                    f"[magenta]UUID[/magenta]: {app_data['organisation']}"
                ),
                title="Organisation"),
            Panel(
                (
                    f"[magenta]Name[/magenta]: {app_meta['plan_group_name']}\n"
                    f"[magenta]UUID[/magenta]: {app_data['plan_group']}"
                ), 
                title="Plan group"),
            Panel(
                (
                    f"[magenta]Name[/magenta]: {app_meta['region_name']}\n"
                    f"[magenta]UUID[/magenta]: {app_data['region']}"
                ), 
                title="Region"),
            Panel(
                (
                    f"[magenta]URL[/magenta]: {app_data['project_template']}"
                ) if app_data["project_template"] else "—", 
                title="Project template"),
            Panel(release_commands_summary, title="Release commands"),
            Panel(
                (
                    f"[magenta]URL[/magenta]: {app_meta['repository_url']}\n"
                    f"[magenta]Branch[/magenta]: {app_data['branch']}\n"
                    f"[magenta]UUID[/magenta]: {app_data['repository']}"
                ) if app_data.get("repository") else "—", 
                title="Repository"),
            Panel(str(app_meta["deploy"]), title="Deploy"),
        )
        for panel in app_details.renderables:
            panel.title_align = "left"
            panel.border_style = "green"

        app_details = Panel(
            app_details,
            title = "Application details",
            title_align = "left",
            expand = False,
        )

    console.print(app_details)


def build_app_url(client, app_uuid):
    host = client.session.host
    app = client.get_application(app_uuid)
    org = app["organisation"]
    uuid = app["uuid"]

    app_url = "/".join([host, "o", org, "app", uuid])

    return app_url
