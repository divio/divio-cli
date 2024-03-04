from __future__ import annotations

import time

import inquirer
from click import prompt

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
    "detected_template_release_commands": (
        "Your chosen template requires the following release commands:"
    ),
    "include_template_release_commands": (
        "Do you want to include them? Your application will not be able to "
        "deploy successfully without them."
    ),
    "detected_template_services": (
        "Your chosen template requires the following services:"
    ),
    "include_template_services": (
        "Do you want to include them? Your application will not be able to "
        "deploy successfully without them."
    ),
    "create_release_commands": "Want to create custom release commands for your application?",
    "enter_release_command_label": "Enter the label of your release command",
    "enter_release_command": "Enter your release command",
    "add_another_release_command": "Want to add another release command?",
    # External repository
    "repo_connect": "Want to connect an external repository to your application?",
    "repo_url_enter": "Enter the URL of your external repository",
    "repo_branch_enter": "Enter the name of your target branch",
    "repo_ssh_key_type_select": (
        "SSH verification requires a specific key type. Please select one"
    ),
    "repo_host_username_enter": "Enter the username of your repository host",
    "repo_host_password_enter": "Enter the password of your repository host (your input is not displayed)",
    "create_deploy_key": (
        "Please register this ssh key with your repository provider. See "
        "https://docs.divio.com/how-to/resources-configure-git/#add-your-application-s-public-key-to-the-git-host "
        "for more information. Ready to continue?"
    ),
    "repository_verification_skipped": "Repository verification skipped. No repository connected.",
    "repo_verification_timeout": "Repository verification timeout.",
    "repo_verification_failed": "Repository verification failed.",
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


def app_details_summary(
    data: dict,
    metadata: dict,
    services: [dict] | None = None,
    deploy: bool = False,
    as_json: bool = False,
) -> str | dict:
    """
    Creates either a human readable or a JSON representation of the
    application details.

    Parameters:
    - data (dict): Application data.
    - metadata (dict): Application metadata.
    - deploy (bool): Trigger deployment of the 'test' environment.
    - as_json (bool): Return a JSON representation of the application details.

    Returns:
    - app_details (str | dict): A Human readable or a JSON representation of
    the application details.
    """

    if as_json:
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
                "branch": data["branch"] if data["repository"] else None,
                "uuid": data["repository"],
            },
            "release_commands": data["release_commands"],
            "services": services,
            "deploy": deploy,
        }
    else:
        template_display = (
            (
                f"Template: {data['app_template']} ({metadata['template_uuid']})"
                if metadata["template_uuid"]
                else f"Template: {data['app_template']}"
            )
            if data["app_template"]
            else "Template: —"
        )

        repository_display = (
            (
                f"Repository: ({data['repository']})\n  "
                f"URL: {metadata['repo_url']}\n  "
                f"Branch: {data['branch']}"
            )
            if data["repository"]
            else "Repository: —"
        )

        services_display = (
            "Services:"
            + "".join([f"\n  {s['name']} ({s['uuid']})" for s in services])
            if services
            else "Services: —"
        )

        release_commands_display = (
            "Release commands:"
            + "".join(
                [
                    f"\n  {rc['label']}: {rc['command']}"
                    for rc in data["release_commands"]
                ]
            )
            if data["release_commands"]
            else "Release commands: —"
        )

        app_details = [
            f"Name: {data['name']}",
            f"Slug: {data['slug']}",
            f"Organisation: {metadata['org_name']} ({data['organisation']})",
            f"Plan Group: {metadata['plan_group_name']} ({data['plan_group']})",
            f"Region: {metadata['region_name']} ({data['region']})",
            template_display,
            repository_display,
            release_commands_display,
            f"Deploy (test environment): {'Yes' if deploy else 'No'}",
            services_display,
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


def get_repo_url(client, suggested_url=None):
    repo_url = None
    while True:
        if not repo_url:
            repo_url = prompt(
                APP_WIZARD_MESSAGES["repo_url_enter"],
                default=suggested_url,
            )
        response = client.validate_repository_field("url", repo_url)
        errors = response.get("url")
        if errors:
            for e in errors:
                status_print(e, status="error")
            repo_url = None
        else:
            break

    return repo_url


def verify_app_repo(client, uuid, branch):
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

    # Initiating the celery task to verify the repository.
    client.check_repository(uuid, branch)

    c = 0
    while True:
        repo_state = client.get_repository(uuid)["state"]
        if repo_state in ["INVALID", "CLONED"] or c > 14:
            break
        c += 1
        time.sleep(2)

    if repo_state != "CLONED":
        if repo_state == "CLONING":
            status_print(
                APP_WIZARD_MESSAGES["repo_verification_timeout"], "error"
            )
        else:
            status_print(
                APP_WIZARD_MESSAGES["repo_verification_failed"], "error"
            )
        verification_status = inquirer.prompt(
            options, raise_keyboard_interrupt=True
        )["choice"]
    else:
        # Cloned repository successfully, pull access confirmed.
        # A second check is required to also verify push access.
        response = client.check_repository(uuid, branch)
        if response.get("code") == "success":
            verification_status = "success"
        else:
            status_print(
                APP_WIZARD_MESSAGES["repo_verification_failed"], "error"
            )
            verification_status = inquirer.prompt(
                options, raise_keyboard_interrupt=True
            )["choice"]

    return verification_status
