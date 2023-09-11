from rich import box
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.json import JSON
from .utils import status_print, slugify
import inquirer
import time
import json
import secrets

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
    "invalid_organisation": "Invalid organization.",
    # Plan group
    "select_plan_group": "Select a plan for your application",
    "plan_group_missing": (
        "Error: Missing option '-p' / '--plan-group'. "
        "Required in non-interactive mode."
    ),
    "invalid_plan_group": "Invalid plan.",
    # Region
    "select_region": "Select a region for your application",
    "region_missing": (
        "Error: Missing option '-r' / '--region'. "
        "Required in non-interactive mode."
    ),
    "invalid_region": "Invalid region.",
    # Template
    "create_template": "Want to add a template to your application?",
    "select_template": "Select a template for your application",
    "enter_template_url": "Enter the URL of your template",
    # Release commands
    "create_release_commands": "Want to create custom release commands for your application?",
    "enter_release_command_label": "Enter the label of your release command",
    "enter_release_command": "Enter your release command",
    "add_another_release_command": "Want to add another release command?",
    # Custom repository
    "connect_repository": "Want to connect an external repository to your application?",
    "enter_repository_url": "Enter the URL of your custom repository",
    "enter_repository_branch": "Enter the name of your target branch",
    "select_repository_ssh_key_type": "Select the type of your deploy key",
    "create_deploy_key": (
        "Please register this ssh key with your repository provider. Ready to continue?"
    ),
    "repository_verification_skipped": "Repository verification skipped. No repository connected.",
    "repository_verification_timeout": "Repository verification timeout.",
    "confirm_app_creation": "Confirm application creation to proceed.",
    # Deploy
    "deployment_triggered": "Deployment of 'test' environment triggered.",
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
            box=box.SIMPLE,
        )
        table.add_column("Label", style="magenta")
        table.add_column("Command", style="cyan")
        for rc in release_commands:
            table.add_row(rc['label'], rc["command"])


        return table


def print_app_details_summary(data, metadata, as_json=False):
    """Return a table of application details."""

    if as_json:
        app_details = {
            "name": data["name"],
            "slug": data["slug"],
            "organisation": {
                "name": metadata["organisation_name"],
                "uuid": data["organisation"],
            },
            "plan_group": {
                "name": metadata["plan_group_name"],
                "uuid": data["plan_group"],
            },
            "region": {
                "name": metadata["region_name"],
                "uuid": data["region"],
            },
            "template": data["app_template"],
            "release_commands": data["release_commands"],
            "repository": {
                "url": metadata["repository_url"],
                "branch": data["branch"],
            } if data.get("repository") else {},
            "deploy": metadata["deploy"],
        }

        console.rule("Application details")
        console.print(JSON(json.dumps(app_details)))
        console.rule()
    else:
        release_commands_summary = create_app_release_commands_summary(
            data["release_commands"]
        ) or "—"

        app_details_group = Group(
            Panel(data["name"], title="Name"),
            Panel(data["slug"], title="Slug"),
            Panel(
                f"name: {metadata['organisation_name']}\nuuid: {data['organisation']}",
                title="Organisation"
            ),
            Panel(
                f"name: {metadata['plan_group_name']}\nuuid: {data['plan_group']}",
                title="Plan group"
            ),
            Panel(
                f"name: {metadata['region_name']}\nuuid: {data['region']}",
                title="Region"
            ),
            Panel(data["app_template"] or "—", title="Template"),
            Panel(release_commands_summary, title="Release commands"),
            Panel(
                f"url: {metadata['repository_url']}\nbranch: {data['branch']}\nuuid: {data['repository']}"
                if data.get("repository") else "—",
                title="Repository"
            ),
            Panel(
                "Activated" if metadata["deploy"] else "Deactivated",
                title="Deploy (test environment)"
            ),
        )
        
        for panel in app_details_group.renderables:
            panel.title_align = "left"
            panel.border_style = "green"

        app_details = Panel(
            app_details_group,
            box = box.MINIMAL,
            expand = False,
            padding = 0,
            width = 80,
        )

        console.print(app_details)

def build_app_url(client, app_uuid):
    host = client.session.host
    app = client.get_application(app_uuid)
    org = app["organisation"]
    uuid = app["uuid"]

    app_url = "/".join([host, "o", org, "app", uuid])

    return app_url

def suggest_app_slug(client, name):
    slugified_name = slugify(name)
    suggested_slug = slugified_name
    response = client.validate_application_field("slug", suggested_slug)
    
    # For the slug to be present in the response, it means that
    # it failed validation and we need to suggest a new one.
    if response.get("slug"):
        while True:
            suggested_slug = f"{slugified_name}-{secrets.token_hex()[:5]}"
            response = client.validate_application_field("slug", suggested_slug)
            if not response.get("slug"):
                break

    return suggested_slug



def verify_app_repository(client, verbose, uuid, branch, url):
    c = 0
    response = client.check_repository(
        uuid, branch
    )
    with console.status("Verifying repository..."):
        while response["code"] == "waiting" and c < 5:
            time.sleep(5)
            response = client.check_repository(
                uuid, branch
            )
            c += 1

    if response["code"] == "waiting":
        status_print(
            APP_WIZARD_MESSAGES[
                "repository_verification_timeout"
            ],
            status="error",
        )
        # TODO: Delete the repository before exiting.
    elif response["code"] != "success":
        status_print(
            f"{response['non_field_errors'][0]}",
            status="error",
        )
        # TODO: Delete the repository before exiting.
    else:
        if verbose:
            status_print(
                f"Verified repository: {url!r}",
                status="success",
            )

    if response["code"] != "success":
        choices=[
            ("Retry repository verification", "retry"),
            ("Restart repository connection", "restart"),
            ("Skip this step (no repository)", "skip"),
        ]
        options = [
            inquirer.List(
            "choice",
            message="How would you like to proceed?",
            choices=choices,
            )
        ]
        verification_status = inquirer.prompt(options)["choice"]
    else:
        verification_status = "success"

    return verification_status

    