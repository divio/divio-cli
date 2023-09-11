import sys
import inquirer
from .utils import status_print
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from .wizards_utils import (
    APP_WIZARD_MESSAGES,
    AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
    create_app_release_commands_summary,
    log_app_details_summary,
    verify_app_repository,
    suggest_app_slug,
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
                response = self.client.validate_application_field("name", name)
                name_errors = response.get("name")
                if name_errors:
                    for err in name_errors:
                        status_print(err, status="error")
                    sys.exit(1)
        else:
            while True:
                if not name:
                    name = Prompt.ask(APP_WIZARD_MESSAGES["enter_name"])

                response = self.client.validate_application_field("name", name)
                name_errors = response.get("name")
                if name_errors:
                    for error in name_errors:
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
                response = self.client.validate_application_field("slug", slug)
                slug_errors = response.get("slug")
                if slug_errors:
                    for error in slug_errors:
                        status_print(error, status="error")
                    sys.exit(1)
        else:
            # Create a valid initial slug suggestion.
            suggested_slug = suggest_app_slug(self.client, name)
            while True:
                if not slug:
                    slug = Prompt.ask(
                        APP_WIZARD_MESSAGES["enter_slug"],
                        default=suggested_slug,
                    )

                response = self.client.validate_application_field("slug", slug)
                slug_errors = response.get("slug")
                if slug_errors:
                    for error in slug_errors:
                        status_print(error, status="error")
                    suggested_slug = suggest_app_slug(self.client, name)
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
        template_release_commands = None

        divio_templates, _ = self.client.get_application_templates()
        divio_templates = {
            t["uuid"]: {
                "name": t["name"],
                "url": t["url"],
            }
            for t in
            divio_templates
        }

        # Non-interactive mode
        if not self.interactive:
            if not template:
                return None, None

            response = self.client.validate_application_field("app_template", template)
            template_errors = response.get("app_template")
            if template_errors:
                for error in template_errors:
                    # Hacky way to convert the default error  
                    # message provided by Django's URLField.
                    if error == "Enter a valid URL.":
                        error = "Invalid URL."
                    status_print(error, status="error")
                sys.exit(1)
        # Interactive mode.
        else:
            choices=[
                ("Select a Divio template", "select"),
                ("Enter a custom template", "custom"),
                ("Skip this step", "skip"),
            ]
            options = [
                inquirer.List(
                "choice",
                message="Want to add a template to your application?",
                choices=choices,
                )
            ]
            create_template = "custom" if template else inquirer.prompt(options)["choice"]

            # No template
            if create_template == "skip":
                return None, None
            # Divio template
            elif create_template == "select":
                divio_templates_options = [
                    inquirer.List(
                        "uuid",
                        message=APP_WIZARD_MESSAGES[
                            "select_template"
                        ],
                        choices=[
                            (divio_templates[t]["name"], t)
                            for t in divio_templates
                        ],
                    )
                ]
                template_uuid = inquirer.prompt(divio_templates_options)["uuid"]
                template = divio_templates[template_uuid]["url"]

                template_release_commands = self.client.get_application_template(
                    template_uuid
                )["release_commands"]
            # Custom template
            else:
                while True:
                    if not template:
                        template = Prompt.ask(
                            APP_WIZARD_MESSAGES["enter_template_url"]
                        )
                    response = self.client.validate_application_field("app_template", template)
                    template_errors = response.get("app_template")
                    if template_errors:
                        for error in template_errors:
                            if error == "Enter a valid URL.":
                                error = "Invalid URL."
                            status_print(error, status="error")
                        template = None
                    else:
                        # There is a chance that the user entered a Divio template URL.
                        # If so, we need to fetch the release commands for that template.
                        for t in divio_templates:
                            if divio_templates[t]["url"] == template:
                                template_release_commands = self.client.get_application_template(
                                    t
                                )["release_commands"]
                                break
                        break

        if template and self.verbose:
            status_print(
                f"Template: {template!r}",
                status="success",
            )

        if template_release_commands and self.verbose:
            template_release_commands_summary = create_app_release_commands_summary(
                template_release_commands, as_json=self.as_json
            )
            if self.as_json:
                console.rule("Template release commands")
                console.print(template_release_commands_summary)
                console.rule()
            else:
                template_release_commands_summary.title = "Template release commands:"
                template_release_commands_summary.title_justify = "left"
                console.print(template_release_commands_summary)

        return template, template_release_commands

    def get_release_commands(self, template_release_commands):
        release_commands = template_release_commands.copy() or []
        
        if not self.interactive:
            return release_commands

        if Confirm.ask(
            APP_WIZARD_MESSAGES["create_release_commands"],
            default=False,
        ):
            add_another = True
            while add_another:
                # Retrieve and validate the release command label.
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

                if self.verbose:
                    status_print(
                        f"Release command: {release_command_label!r}",
                        status="success",
                    )
                add_another = Confirm.ask(
                    APP_WIZARD_MESSAGES["add_another_release_command"],
                    default=False,
                )

        if release_commands and release_commands != template_release_commands and self.verbose:
            release_commands_summary = create_app_release_commands_summary(
                release_commands, as_json=self.as_json
            )
            if self.as_json:
                console.rule("Release commands")
                console.print(release_commands_summary)
                console.rule()
            else:
                release_commands_summary.title = "Release commands:"
                release_commands_summary.title_justify = "left"
                console.print(release_commands_summary)

        return release_commands

    def get_git_repository(self, organisation):
        restart_connection = False
        suggested_repository_url = None
        suggested_repository_branch = "main"

        if not self.interactive:
            return None, None, None

        while True:
            if restart_connection or Confirm.ask(
                APP_WIZARD_MESSAGES["connect_repository"], 
                default=False,
            ):
                # Repository URL
                repository_url = None
                while True:
                    if not repository_url:
                        repository_url = Prompt.ask(
                            APP_WIZARD_MESSAGES["enter_repository_url"],
                            default=suggested_repository_url,
                        )

                    response = self.client.validate_repository_field("url", repository_url)
                    repository_url_errors = response.get("url")
                    if repository_url_errors:
                        for error in repository_url_errors:
                            status_print(error, status="error")

                        repository_url = None
                    else:
                        break
            
                # Repository branch
                repository_branch = Prompt.ask(
                    APP_WIZARD_MESSAGES["enter_repository_branch"],
                    default=suggested_repository_branch,
                )

                # Repository SSH key type
                # TODO: Create a way to retrieve available repository
                # types dynamically, not like a hardcoded list.
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
                # Display the the ssh public key (deploy key) and ask the user to
                # register it with their repository provider.
                console.rule("SSH Key")
                console.print(repository_ssh_key)
                console.rule()

                if Confirm.ask(
                    APP_WIZARD_MESSAGES["create_deploy_key"], 
                    default=True
                ):
                    while True:
                        verification_status = verify_app_repository(
                            self.client,
                            self.verbose,
                            repository_uuid,
                            repository_branch,
                            repository_url,
                        )

                        if verification_status == "retry":
                            continue
                        elif verification_status == "restart":
                            restart_connection = True
                            suggested_repository_url = repository_url
                            suggested_repository_branch = repository_branch
                            break
                        elif verification_status == "skip":
                            status_print(
                                APP_WIZARD_MESSAGES["repository_verification_skipped"],
                                status="warning",
                            )
                            return None, None, None
                        else:
                            return repository_uuid, repository_url, repository_branch
            else:
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
                console.print("Aborted.", style="red")
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
