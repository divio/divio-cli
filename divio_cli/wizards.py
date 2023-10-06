import json
import sys

import inquirer
from click import confirm
from rich.console import Console
from rich.json import JSON
from rich.prompt import Prompt

from .utils import status_print
from .wizards_utils import (
    APP_WIZARD_MESSAGES,
    AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
    app_details_summary,
    build_app_url,
    suggest_app_slug,
    verify_app_repo,
)


console = Console()


class CreateAppWizard:
    def __init__(self, obj):
        self.client = obj.client
        self.interactive = obj.interactive
        self.verbose = obj.verbose
        self.as_json = obj.as_json
        self.metadata = obj.metadata

        if self.verbose and self.interactive:
            console.print(APP_WIZARD_MESSAGES["welcome_message"])

    def get_name(self, name):
        if not self.interactive:
            if not name:
                status_print(
                    APP_WIZARD_MESSAGES["name_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                response = self.client.validate_application_field("name", name)
                errors = response.get("name")
                if errors:
                    for e in errors:
                        status_print(e, status="error")
                    sys.exit(1)
        else:
            while True:
                if not name:
                    name = Prompt.ask(APP_WIZARD_MESSAGES["name_enter"])

                response = self.client.validate_application_field("name", name)
                errors = response.get("name")
                if errors:
                    for e in errors:
                        status_print(e, status="error")
                    name = None
                else:
                    break

        return name

    def get_slug(self, slug, name):
        if not self.interactive:
            if not slug:
                status_print(
                    APP_WIZARD_MESSAGES["slug_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                response = self.client.validate_application_field("slug", slug)
                errors = response.get("slug")
                if errors:
                    for e in errors:
                        status_print(e, status="error")
                    sys.exit(1)
        else:
            suggested_slug = suggest_app_slug(self.client, name)
            while True:
                if not slug:
                    slug = Prompt.ask(
                        APP_WIZARD_MESSAGES["slug_enter"],
                        default=suggested_slug,
                    )

                response = self.client.validate_application_field("slug", slug)
                errors = response.get("slug")
                if errors:
                    for e in errors:
                        status_print(e, status="error")
                    slug = None
                else:
                    break

        return slug

    def get_org(self, org):
        user_orgs, _ = self.client.get_organisations()
        orgs_uuid_name_mapping = {
            org["uuid"]: org["name"] for org in user_orgs
        }

        if not self.interactive:
            if not org:
                status_print(
                    APP_WIZARD_MESSAGES["org_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if org not in orgs_uuid_name_mapping:
                    status_print(
                        APP_WIZARD_MESSAGES["org_invalid"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not org:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES["org_select"],
                            choices=[
                                (f"{org['name']} ({org['uuid']})", org["uuid"])
                                for org in user_orgs
                            ],
                            carousel=True,
                        )
                    ]
                    org = inquirer.prompt(
                        options, raise_keyboard_interrupt=True
                    )["uuid"]

                if org not in orgs_uuid_name_mapping:
                    status_print(
                        APP_WIZARD_MESSAGES["org_invalid"],
                        status="error",
                    )
                    org = None
                else:
                    break

        return org, orgs_uuid_name_mapping[org]

    def get_plan_group(self, plan_group, org):
        user_plan_groups, _ = self.client.get_application_plan_groups(
            params={"organisation": org}
        )
        plan_groups_uuid_name_mapping = {
            pg["uuid"]: pg["name"] for pg in user_plan_groups
        }

        if not self.interactive:
            if not plan_group:
                status_print(
                    APP_WIZARD_MESSAGES["plan_group_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if plan_group not in plan_groups_uuid_name_mapping:
                    status_print(
                        APP_WIZARD_MESSAGES["plan_group_invalid"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not plan_group:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES["plan_group_select"],
                            choices=[
                                (f"{pg['name']} ({pg['uuid']})", pg["uuid"])
                                for pg in user_plan_groups
                            ],
                            carousel=True,
                        )
                    ]
                    plan_group = inquirer.prompt(
                        options, raise_keyboard_interrupt=True
                    )["uuid"]

                if plan_group not in plan_groups_uuid_name_mapping:
                    status_print(
                        APP_WIZARD_MESSAGES["plan_group_invalid"],
                        status="error",
                    )
                    plan_group = None
                else:
                    break

        return plan_group, plan_groups_uuid_name_mapping[plan_group]

    def get_region(self, region, plan_group):
        user_regions_uuids = self.client.get_application_plan_group(
            plan_group
        )["regions"]
        user_regions, _ = self.client.get_regions(
            params={"uuid": user_regions_uuids}
        )
        regions_uuid_name_mapping = {
            region["uuid"]: region["name"] for region in user_regions
        }

        if not self.interactive:
            if not region:
                status_print(
                    APP_WIZARD_MESSAGES["region_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if region not in user_regions_uuids:
                    status_print(
                        APP_WIZARD_MESSAGES["region_invalid"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not region:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES["region_select"],
                            choices=[
                                (f"{org['name']} ({org['uuid']})", org["uuid"])
                                for org in user_regions
                            ],
                            carousel=True,
                        )
                    ]
                    region = inquirer.prompt(
                        options, raise_keyboard_interrupt=True
                    )["uuid"]
                if region not in user_regions_uuids:
                    status_print(
                        APP_WIZARD_MESSAGES["region_invalid"],
                        status="error",
                    )
                    region = None
                else:
                    break

        return region, regions_uuid_name_mapping[region]

    def get_template(self, template):
        template_uuid = None
        template_release_commands = None

        divio_templates, _ = self.client.get_application_templates()
        divio_templates = {
            t["uuid"]: {
                "name": t["name"],
                "url": t["url"],
            }
            for t in divio_templates
        }

        # Non-interactive mode
        if not self.interactive:
            if not template:
                return None, None, None

            response = self.client.validate_application_field(
                "app_template", template
            )
            errors = response.get("app_template")
            if errors:
                for e in errors:
                    # Hacky way to convert the default error
                    # message provided by Django's URLField.
                    if e == "Enter a valid URL.":
                        e = "Invalid template URL."
                    status_print(e, status="error")
                sys.exit(1)

            for t in divio_templates:
                if divio_templates[t]["url"] == template:
                    template_uuid = t
                    template_release_commands = (
                        self.client.get_application_template(t)[
                            "release_commands"
                        ]
                    )
        # Interactive mode.
        else:
            options = [
                inquirer.List(
                    "choice",
                    message="Want to add a template to your application?",
                    choices=[
                        ("Select a Divio template", "select"),
                        ("Enter a custom template", "custom"),
                        ("Skip this step", "skip"),
                    ],
                    carousel=True,
                )
            ]

            create_template = (
                "custom"
                if template
                else inquirer.prompt(options, raise_keyboard_interrupt=True)[
                    "choice"
                ]
            )

            # No template
            if create_template == "skip":
                return None, None, None
            # Divio template
            elif create_template == "select":
                divio_template_options = [
                    inquirer.List(
                        "uuid",
                        message=APP_WIZARD_MESSAGES["template_select"],
                        choices=[
                            (f"{divio_templates[t]['name']} ({t})", t)
                            for t in divio_templates
                        ],
                        carousel=True,
                    )
                ]
                template_uuid = inquirer.prompt(
                    divio_template_options, raise_keyboard_interrupt=True
                )["uuid"]
                template = divio_templates[template_uuid]["url"]

                template_release_commands = (
                    self.client.get_application_template(template_uuid)[
                        "release_commands"
                    ]
                )
            # Custom template
            else:
                while True:
                    if not template:
                        template = Prompt.ask(
                            APP_WIZARD_MESSAGES["template_enter_url"]
                        )
                    response = self.client.validate_application_field(
                        "app_template", template
                    )
                    errors = response.get("app_template")
                    if errors:
                        for e in errors:
                            if e == "Enter a valid URL.":
                                e = "Invalid template URL."
                            status_print(e, status="error")
                        template = None
                    else:
                        # There is a chance that the user entered a Divio template URL.
                        # If so, we need to fetch the release commands for that template.
                        for t in divio_templates:
                            if divio_templates[t]["url"] == template:
                                template_uuid = t
                                template_release_commands = (
                                    self.client.get_application_template(t)[
                                        "release_commands"
                                    ]
                                )
                                break
                        break

        return template, template_uuid, template_release_commands

    def get_release_commands(self, template_release_commands):
        release_commands = (
            template_release_commands.copy()
            if template_release_commands
            else []
        )

        if not self.interactive:
            return release_commands

        if confirm(
            APP_WIZARD_MESSAGES["create_release_commands"],
        ):
            add_another = True
            while add_another:

                # Retrieve and validate the release command label.
                while True:
                    release_command_label = Prompt.ask(
                        APP_WIZARD_MESSAGES["enter_release_command_label"]
                    )
                    if release_command_label in [
                        d["label"] for d in release_commands
                    ]:
                        status_print(
                            (
                                f"Release command with label {release_command_label!r} "
                                "already exists. All labels must be unique."
                            ),
                            status="error",
                        )
                        release_command_label = None
                    else:
                        break

                # Release command value.
                release_command_value = Prompt.ask(
                    APP_WIZARD_MESSAGES["enter_release_command"]
                )

                release_commands.append(
                    {
                        "label": release_command_label,
                        "command": release_command_value,
                    }
                )

                add_another = confirm(
                    APP_WIZARD_MESSAGES["add_another_release_command"],
                )

        return release_commands

    def get_git_repo(self, org):
        if not self.interactive:
            return None, None, None

        restart_connection = False
        suggested_repo_url = None
        suggested_repo_branch = "main"

        while True:
            if restart_connection or confirm(
                APP_WIZARD_MESSAGES["repo_connect"],
            ):
                # Repository URL
                repo_url = None
                while True:
                    if not repo_url:
                        repo_url = Prompt.ask(
                            APP_WIZARD_MESSAGES["repo_url_enter"],
                            default=suggested_repo_url,
                        )

                    response = self.client.validate_repository_field(
                        "url", repo_url
                    )
                    errors = response.get("url")
                    if errors:
                        for e in errors:
                            status_print(e, status="error")
                        repo_url = None
                    else:
                        break

                # Repository branch
                repo_branch = Prompt.ask(
                    APP_WIZARD_MESSAGES["repo_branch_enter"],
                    default=suggested_repo_branch,
                )

                # Repository SSH key type
                # TODO: Create a way to retrieve available repository
                # types dynamically, not like a hardcoded list.
                ssh_key_type_options = [
                    inquirer.List(
                        "key",
                        message=APP_WIZARD_MESSAGES[
                            "repo_ssh_key_type_select"
                        ],
                        choices=AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
                        carousel=True,
                    )
                ]
                repo_ssh_key_type = inquirer.prompt(
                    ssh_key_type_options, raise_keyboard_interrupt=True
                )["key"]

                # Create the repository.
                response = self.client.create_repository(
                    org, repo_url, repo_ssh_key_type
                )
                repo_uuid = response["uuid"]
                repository_ssh_key = response["auth_info"]
                # Display the the ssh public key (deploy key) and ask the user to
                # register it with their repository provider.
                console.rule("SSH Key")
                console.print(repository_ssh_key)
                console.rule()

                if confirm(
                    APP_WIZARD_MESSAGES["create_deploy_key"], default=True
                ):
                    while True:
                        verification_status = verify_app_repo(
                            self.client,
                            self.verbose,
                            repo_uuid,
                            repo_branch,
                            repo_url,
                        )

                        if verification_status == "retry":
                            continue

                        if verification_status == "restart":
                            restart_connection = True
                            suggested_repo_url = repo_url
                            suggested_repo_branch = repo_branch
                            break

                        if verification_status == "skip":
                            status_print(
                                APP_WIZARD_MESSAGES[
                                    "repository_verification_skipped"
                                ],
                                status="warning",
                            )
                            return None, None, None
                        # Success
                        else:
                            return (
                                repo_uuid,
                                repo_url,
                                repo_branch,
                            )
            else:
                return None, None, None

    def get_services(self, template_uuid=None):
        if not template_uuid:
            return None

        return self.client.get_application_template(template_uuid)["services"]

    def create_app(self, data):
        """
        Responsible for:
        - Creating the application based on the user provided data.
        - Triggering the deployment of the test environment, if requested.
        - Displaying the application details depending on the verbosity level.
        """

        if not self.interactive:
            response = self.client.application_create(data=data)
            app_url = build_app_url(self.client, response["uuid"])
            app_details = app_details_summary(
                data, self.metadata, as_json=self.as_json
            )
            app_details["app_url"] = app_url
            if self.verbose:
                if self.as_json:
                    console.print(
                        JSON(
                            json.dumps(app_details), indent=4, highlight=False
                        )
                    )
                else:
                    console.rule("Application Details")
                    console.print(app_details)
                    console.rule()
        else:
            if self.verbose:
                app_details = app_details_summary(
                    data, self.metadata, as_json=self.as_json
                )
                console.rule("Application Details")
                console.print(
                    JSON(json.dumps(app_details), indent=4)
                    if self.as_json
                    else app_details
                )
                console.rule()

            if confirm(
                APP_WIZARD_MESSAGES["confirm_app_creation"],
                default=True,
            ):
                response = self.client.application_create(data=data)
            else:
                console.print("Aborted.", style="red")
                sys.exit(0)

            if self.verbose and self.interactive:
                app_url = build_app_url(self.client, response["uuid"])
                status_print(
                    f"Application created! Visit here: {app_url}",
                    status="success",
                )

        if self.metadata["deploy"]:
            app_envs = self.client.get_environments(
                params={"application": response["uuid"], "slug": "test"},
            )
            self.client.deploy_environment(app_envs["results"][0]["uuid"])
            if self.verbose and self.interactive:
                status_print(
                    APP_WIZARD_MESSAGES["deployment_triggered"],
                    status="success",
                )

        template_uuid = self.metadata["template_uuid"]
        if template_uuid:
            template_services = self.get_services(template_uuid)
            if template_services and self.verbose and self.interactive:
                status_print(
                    APP_WIZARD_MESSAGES["services_not_supported"],
                    status="warning",
                )
