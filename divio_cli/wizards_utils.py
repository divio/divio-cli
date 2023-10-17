from __future__ import annotations

import time

import inquirer

from .utils import slugify, status_print


APP_WIZARD_MESSAGES = {
    # Welcome
    "welcome_message": (
        "Welcome to the application creation wizard where you'll be "
        "guided through the process of creating a new Divio application. "
        "You'll be now prompted to enter the required information.\n"
    ),
    # Name
    "name_enter": "Enter the name of your application",
    "name_missing": (
        "Missing option '-n' / '--name'. Required in non-interactive mode."
    ),
    # Slug
    "slug_enter": "Enter the slug of your application",
    "slug_missing": (
        "Missing option '-s' / '--slug'. Required in non-interactive mode."
    ),
    # Organisation
    "orgs_not_found": "No organisations found. Please create an organisation first.",
    "org_select": "Select an organisation for your application",
    "org_missing": (
        "Missing option '-o' / '--organisation'. "
        "Required in non-interactive mode."
    ),
    "org_invalid": "Invalid organization.",
    # Plan group
    "plan_group_select": "Select a plan for your application",
    "plan_group_missing": (
        "Missing option '-p' / '--plan-group'. "
        "Required in non-interactive mode."
    ),
    "plan_group_invalid": "Invalid plan.",
    # Region
    "region_select": "Select a region for your application",
    "region_missing": (
        "Missing option '-r' / '--region'. "
        "Required in non-interactive mode."
    ),
    "region_invalid": "Invalid region.",
    # Template
    "create_template": "Want to add a template to your application?",
    "template_select": "Select a template for your application",
    "template_enter_url": "Enter the URL of your template",
    # Release commands
    "create_release_commands": "Want to create custom release commands for your application?",
    "enter_release_command_label": "Enter the label of your release command",
    "enter_release_command": "Enter your release command",
    "add_another_release_command": "Want to add another release command?",
    # Custom repository
    "repo_connect": "Want to connect an external repository to your application?",
    "repo_url_enter": "Enter the URL of your custom repository",
    "repo_branch_enter": "Enter the name of your target branch",
    "repo_ssh_key_type_select": "Select the type of your deploy key",
    "create_deploy_key": (
        "Please register this ssh key with your repository provider. Ready to continue?"
    ),
    "repository_verification_skipped": "Repository verification skipped. No repository connected.",
    "repo_verification_timeout": "Repository verification timeout.",
    "confirm_app_creation": "Confirm application creation to proceed.",
    # Deploy
    "deployment_triggered": "Deployment of 'test' environment triggered.",
    # Services
    "services_not_supported": (
        "Detected required services due to the selected template. "
        "Services are not supported yet in the application creation wizard. "
        "Please use the Divio Control Panel to add those services to your application. "
        "Otherwise, you will not be able to deploy your application successfully."
    ),
}

AVAILABLE_REPOSITORY_SSH_KEY_TYPES = [
    "ED25519",
    "ECDSA",
    "RSA",
]


def get_release_commands_display(
    release_commands: list[dict],
    template_release_commands: list[dict],
    as_json: bool = False,
) -> str | list[dict]:
    """
    Return a human readable version of all release commands
    (custom and template release commands, if any).

    Parameters:
    - release_commands (list[dict]): List of release commands provided by the
    user.
    - template_release_commands (list[dict]): List of release commands provided
    by the template, if any.
    """

    if not (release_commands or template_release_commands):
        return None if as_json else "Release commands: —"

    template_release_commands_labels = (
        [rc["label"] for rc in template_release_commands]
        if template_release_commands
        else []
    )

    if as_json:
        return [
            {
                "label": rc["label"],
                "command": rc["command"],
                "from_template": rc["label"]
                in template_release_commands_labels
                or False,
            }
            for rc in release_commands
        ]

    release_commands_display = ""
    for rc in release_commands:
        from_template = (
            "Yes" if rc["label"] in template_release_commands_labels else "No"
        )
        release_commands_display += (
            f"  {rc['label']}:\n    "
            f"Command: {rc['command']}\n    "
            f"From Template: {from_template}\n"
        )

    return f"Release commands:\n{release_commands_display}".strip()


def app_details_summary(
    data: dict, metadata: dict, deploy: bool = False, as_json: bool = False
) -> str | dict:
    """
    Creates either a human readable summary or a JSON representation of the
    application details.

    Parameters:
    - data (dict): Application data.
    - metadata (dict): Application metadata.
    - deploy (bool): Trigger deployment of the 'test' environment.
    - as_json (bool): Return a JSON representation of the application details.

    Returns:
    - app_details (str | dict): Human readable summary or JSON representation
    of the application details.
    """

    release_commands_display = get_release_commands_display(
        data["release_commands"],
        metadata["template_release_commands"],
        as_json=as_json,
    )

    if as_json:
        repo_branch_display = data["branch"] if data["repository"] else None
        app_details = {
            "name": data["name"],
            "slug": data["slug"],
            "organisation": {
                "name": metadata["org_name"],
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
            "template": {
                "url": data["app_template"],
                "uuid": metadata["template_uuid"],
            },
            "repository": {
                "url": metadata["repo_url"],
                "branch": repo_branch_display,
                "uuid": data["repository"],
            },
            "deploy": deploy,
            "release_commands": release_commands_display,
        }
    else:
        repo_branch_display = data["branch"] if data["repository"] else "—"
        app_details = [
            f"Name: {data['name']}",
            f"Slug: {data['slug']}",
            (
                "Organisation: \n  "
                f"Name: {metadata['org_name']}\n  "
                f"UUID: {data['organisation']}"
            ),
            (
                "Plan Group: \n  "
                f"Name: {metadata['plan_group_name']}\n  "
                f"UUID: {data['plan_group']}"
            ),
            (
                "Region: \n  "
                f"Name: {metadata['region_name']}\n  "
                f"UUID: {data['region']}"
            ),
            (
                "Template: \n  "
                f"URL: {data['app_template']}\n  "
                f"UUID: {metadata['template_uuid'] or '—'}"
            )
            if data["app_template"]
            else "Template: —",
            (
                "Repository: \n  "
                f"URL: {metadata['repo_url']}\n  "
                f"Branch: {repo_branch_display}\n  "
                f"UUID: {data['repository']}"
            )
            if data["repository"]
            else "Repository: —",
            f"Deploy (test environment): {'Yes' if deploy else 'No'}",
            release_commands_display,
        ]
        app_details = "\n".join(app_details)

    return app_details


def build_app_url(client, app_uuid):
    host = client.session.host
    app = client.get_application(app_uuid)
    org = app["organisation"]
    uuid = app["uuid"]

    return f"{host}/o/{org}/app/{uuid}"


def suggest_app_slug(client, app_name):
    slug = slugify(app_name)
    response = client.validate_application_field("slug", slug)
    if response.get("slug"):
        return None

    return slug


def verify_app_repo(client, uuid, branch):
    c = 0
    response = client.check_repository(uuid, branch)
    while response["code"] == "waiting" and c < 5:
        time.sleep(5)
        response = client.check_repository(uuid, branch)
        c += 1

    if response["code"] == "waiting":
        # TODO: Delete the repository before exiting.
        status_print(
            APP_WIZARD_MESSAGES["repo_verification_timeout"],
            status="error",
        )
    elif response["code"] != "success":
        # TODO: Delete the repository before exiting.
        status_print(
            f"{response['non_field_errors'][0]}",
            status="error",
        )

    if response["code"] != "success":
        choices = [
            ("Retry repository verification", "retry"),
            ("Restart repository connection", "restart"),
            ("Skip this step (no repository)", "skip"),
        ]
        options = [
            inquirer.List(
                "choice",
                message="How would you like to proceed?",
                choices=choices,
                carousel=True,
            )
        ]
        verification_status = inquirer.prompt(
            options, raise_keyboard_interrupt=True
        )["choice"]
    else:
        verification_status = "success"

    return verification_status
