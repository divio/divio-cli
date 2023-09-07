import sys
import time

import click
import inquirer

from .utils import is_valid_template_url, suggest_slug, status_print
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from .wizards_utils import (
    APP_WIZARD_MESSAGES,
    AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
    create_app_release_commands_summary,
    log_app_details_summary,
    build_app_url,
)


console = Console()


class CreateAppWizard:
    def __init__(self, obj):
        self.client = obj.client
        self.interactive = obj.interactive
        self.verbose = obj.verbose
        self.as_json = obj.as_json
        self.metadata = obj.metadata

        if self.verbose:
            console.print(
                Panel(
                    APP_WIZARD_MESSAGES["welcome_message"],
                    title="[bold]Application Creation Wizard",
                    subtitle="[bold]Divio CLI",
                    subtitle_align="right",
                    border_style="green",
                )
            )

    def get_name(self, name):
        if not self.interactive:
            if not name:
                status_print(
                    APP_WIZARD_MESSAGES["name_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                response = self.client.validate_application_name(name)
                validated_name = response.get("name")
                if validated_name != name:
                    for error in validated_name:
                        status_print(error, status="error")
                    sys.exit(1)
        else:
            while True:
                if not name:
                    name = Prompt.ask(APP_WIZARD_MESSAGES["enter_name"])

                response = self.client.validate_application_name(name)
                validated_name = response.get("name")
                if validated_name != name:
                    for error in validated_name:
                        status_print(error, status="error")

                    name = None
                else:
                    break

        if self.verbose:
            status_print(f"Name: {name!r}", status="success")


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
                response = self.client.validate_application_slug(slug)
                validated_slug = response.get("slug")
                if validated_slug != slug:
                    for error in validated_slug:
                        status_print(error, status="error")
                    sys.exit(1)
        else:
            # Create a valid initial slug suggestion.
            suggested_slug = suggest_slug(self.client, name)
            while True:
                if not slug:
                    slug = Prompt.ask(
                        APP_WIZARD_MESSAGES["enter_slug"],
                        default=suggested_slug,
                    )

                response = self.client.validate_application_slug(slug)
                validated_slug = response.get("slug")
                if validated_slug != slug:
                    for error in validated_slug:
                        status_print(error, status="error")
                    suggested_slug = suggest_slug(self.client, name)
                    slug = None
                else:
                    break

        if self.verbose:
            status_print(f"Slug: {slug!r}", status="success")

        return slug

    def get_organisation(self, organisation):
        available_organisations, _ = self.client.get_organisations()
        orgs_uuid_name_mapping = {
            org["uuid"]: org["name"] for org in available_organisations
        }

        if not self.interactive:
            if not organisation:
                status_print(
                    APP_WIZARD_MESSAGES["organisation_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if organisation not in orgs_uuid_name_mapping.keys():
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_organisation"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not organisation:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES[
                                "select_organisation"
                            ],
                            choices=[
                                (org["name"], org["uuid"])
                                for org in available_organisations
                            ],
                        )
                    ]
                    organisation = inquirer.prompt(options)["uuid"]

                if organisation not in orgs_uuid_name_mapping.keys():
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_organisation"],
                        status="error",
                    )
                    organisation = None
                else:
                    break

        organisation_name = orgs_uuid_name_mapping[organisation]
        if self.verbose:
            status_print(
                f"Organisation: {organisation_name!r}",
                status="success",
            )

        return organisation, organisation_name

    def get_plan_group(self, plan_group, organisation):
        available_plan_groups, _ = self.client.get_application_plan_groups(
            params={"organisation": organisation}
        )
        plan_groups_uuid_name_mapping = {
            pg["uuid"]: pg["name"] for pg in available_plan_groups
        }

        if not self.interactive:
            if not plan_group:
                status_print(
                    APP_WIZARD_MESSAGES["plan_group_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if plan_group not in plan_groups_uuid_name_mapping.keys():
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_plan_group"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not plan_group:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES["select_plan_group"],
                            choices=[
                                (pg["name"], pg["uuid"])
                                for pg in available_plan_groups
                            ],
                        )
                    ]
                    plan_group = inquirer.prompt(options)["uuid"]

                if plan_group not in plan_groups_uuid_name_mapping.keys():
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_plan_group"],
                        status="error",
                    )
                    plan_group = None
                else:
                    break

        plan_group_name = plan_groups_uuid_name_mapping[plan_group]
        if self.verbose:
            status_print(
                f"Plan: {plan_group_name!r}",
                status="success",
            )

        return plan_group, plan_group_name

    def get_region(self, region, plan_group):
        available_regions_uuids = self.client.get_application_plan_group(plan_group)[
            "regions"
        ]
        available_regions, _ = self.client.get_regions(
            params={"uuid": available_regions_uuids}
        )
        regions_uuid_name_mapping = {
            region["uuid"]: region["name"] for region in available_regions
        }

        if not self.interactive:
            if not region:
                status_print(
                    APP_WIZARD_MESSAGES["region_missing"],
                    status="error",
                )
                sys.exit(1)
            else:
                if region not in available_regions_uuids:
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_region"],
                        status="error",
                    )
                    sys.exit(1)
        else:
            while True:
                if not region:
                    options = [
                        inquirer.List(
                            "uuid",
                            message=APP_WIZARD_MESSAGES[
                                "select_region"
                            ],
                            choices=[
                                (org["name"], org["uuid"])
                                for org in available_regions
                            ],
                        )
                    ]
                    region = inquirer.prompt(options)["uuid"]
                if region not in available_regions_uuids:
                    status_print(
                        APP_WIZARD_MESSAGES["invalid_region"],
                        status="error",
                    )
                    region = None
                else:
                    break

        region_name = regions_uuid_name_mapping[region]
        if self.verbose:
            status_print(
                f"Region: {region_name!r}",
                status="success",
            )

        return region, region_name

    def get_template(self, template):
        if not self.interactive:
            if not template:
                return None

            if not is_valid_template_url(template):
                status_print(
                    APP_WIZARD_MESSAGES["invalid_template_url"],
                    status="error",
                )
                sys.exit(1)
        else:
            if template or Confirm.ask(
                APP_WIZARD_MESSAGES["create_template"],
                default=False,
            ):
                while True:
                    if not template:
                        template = Prompt.ask(
                            APP_WIZARD_MESSAGES["enter_template"]
                        )
                    # TODO: Validate the template URL against the CP.
                    if not is_valid_template_url(template):
                        status_print(
                            APP_WIZARD_MESSAGES["invalid_template_url"],
                            status="error",
                        )
                        template = None
                    else:
                        break

        if template and self.verbose:
            status_print(
                f"Template: {template!r}",
                status="success",
            )

        return template

    def get_release_commands(self):
        release_commands = []

        if not self.interactive:
            return release_commands

        if Confirm.ask(
            APP_WIZARD_MESSAGES["create_release_commands"],
            default=False,
        ):
            add_another = True
            while add_another:

                while True:
                    release_command_label = Prompt.ask(
                        APP_WIZARD_MESSAGES["enter_release_command_label"]
                    )
                    if release_command_label in [d["label"] for d in release_commands]:
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

                release_command_value = Prompt.ask(
                    APP_WIZARD_MESSAGES["enter_release_command"]
                )
                release_commands.append(
                    {
                        "label": release_command_label,
                        "command": release_command_value,
                    }
                )
                if self.verbose:
                    status_print(
                        f"Release command: {release_command_label!r}",
                        status="success",
                    )
                add_another = Confirm.ask(
                    APP_WIZARD_MESSAGES["add_another_release_command"],
                    default=False,
                )

        if release_commands and self.verbose:
            release_commands_summary = create_app_release_commands_summary(
                release_commands, as_json=self.as_json
            )
            if self.as_json:
                console.rule("Release commands")
                console.print(release_commands_summary)
                console.rule()
            else:
                release_commands_summary.title = "Release commands"
                console.print(release_commands_summary)

        return release_commands

    def get_custom_git_repo(self, organisation):
        if not self.interactive:
            return None, None, None

        if Confirm.ask(
            APP_WIZARD_MESSAGES["connect_repository"], 
            default=False,
        ):
            repository_url = Prompt.ask(
                APP_WIZARD_MESSAGES["enter_repository_url"]
            )
            repository_branch = Prompt.ask(
                APP_WIZARD_MESSAGES["enter_repository_branch"],
                default="main",
            )

            # TODO: Create a CP endpoint to retrieve available repository types
            # dynamically, not like a hardcoded list.
            ssh_key_type_options = [
                inquirer.List(
                    "key",
                    message=APP_WIZARD_MESSAGES["select_repository_ssh_key_type"],
                    choices=AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
                )
            ]
            repository_ssh_key_type = inquirer.prompt(ssh_key_type_options)["key"]

            # Create the repository.
            response = self.client.create_repository(
                organisation, repository_url, repository_ssh_key_type
            )
            repository_uuid = response["uuid"]
            repository_ssh_key = response["auth_info"]
            
            # Ask the user to add the ssh public key (deploy key) to the
            # repository provider.
            console.rule("SSH Key")
            console.print(repository_ssh_key)
            console.rule()
            Confirm.ask(APP_WIZARD_MESSAGES["create_deploy_key"], default=True)

            # Verify the repository.
            c = 0
            response = self.client.check_repository(
                repository_uuid, repository_branch
            )
            with console.status("Verifying repository..."):
                while response["code"] == "waiting" and c < 5:
                    time.sleep(5)
                    response = self.client.check_repository(
                        repository_uuid, repository_branch
                    )
                    c += 1

            if response["code"] == "waiting":
                click.secho(
                    APP_WIZARD_MESSAGES[
                        "repository_verification_timeout"
                    ],
                    fg="red",
                )
                # TODO: Delete the repository before exiting.
                sys.exit(1)
            elif response["code"] != "success":
                click.secho(
                    response["non_field_errors"][0],
                    fg="red",
                )
                # TODO: Delete the repository before exiting.
                sys.exit(1)
            else:
                if self.verbose:
                    click.secho(
                        "SUCCESS: Verified custom repository.", 
                        fg="green"
                    )

            return repository_uuid, repository_url, repository_branch

        return None, None, None

    def create_app(self, data):
        if self.verbose:
            log_app_details_summary(data, self.metadata, as_json=self.as_json)

        if not self.interactive:
            response = self.client.application_create(data=data)
        else:
            if Confirm.ask(
                APP_WIZARD_MESSAGES["confirm_app_creation"],
                default=True,
            ):
                response = self.client.application_create(data=data)
            else:
                click.secho("Aborted.", fg="red")
                sys.exit(0)

        if self.verbose:
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
            if self.verbose:
                status_print(
                    APP_WIZARD_MESSAGES["deployment_triggered"],
                    status="success",
                )
