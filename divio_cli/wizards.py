from __future__ import annotations

import json
import sys

import inquirer
from click import Abort, confirm, echo, prompt, secho
from giturl import parse

from .utils import status_print
from .wizards_utils import (
    APP_WIZARD_MESSAGES,
    AVAILABLE_REPOSITORY_SSH_KEY_TYPES,
    app_details_summary,
    build_app_url,
    get_repo_url,
    suggest_app_slug,
    verify_app_repo,
)


class CreateAppWizard:
    def __init__(self, obj):
        self.client = obj.client
        self.interactive = obj.interactive
        self.verbose = obj.verbose
        self.as_json = obj.as_json
        self.metadata = obj.metadata

        if self.verbose and self.interactive:
            echo(APP_WIZARD_MESSAGES["welcome_message"])

    def get_name(self, name: str) -> str:
        """
        Retrieves and validates the application name provided by the user.

        Parameters:
        - name (str): The application name provided by the user.

        Returns:
        - name (str): The application name, if valid. Otherwise, exits in
        non-interactive mode or prompts the user continuously until a valid
        name is provided in interactive mode.
        """

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
                    name = prompt(APP_WIZARD_MESSAGES["name_enter"])

                response = self.client.validate_application_field("name", name)
                errors = response.get("name")
                if errors:
                    for e in errors:
                        status_print(e, status="error")
                    name = None
                else:
                    break

        return name

    def get_slug(self, slug: str, name: str) -> str:
        """
        Retrieves and validates the application slug provided by the user.
        Also, retrieves the previously validated application name which is
        used to generate a suggested slug.

        Parameters:
        - slug (str): The application slug provided by the user.
        - name (str): The validated application name.

        Returns:
        - slug (str): The application slug, if valid. Otherwise, exits in
        non-interactive mode or prompts the user continuously until a valid
        slug is provided in interactive mode.
        """

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
                    slug = prompt(
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

    def get_org(self, org: str) -> tuple[str, str]:
        """
        Retrieves the organisation UUID from the user and validates it.

        Parameters:
        - org (str): The organisation UUID provided by the user.

        Returns:
        - org (str): The organisation UUID, if valid. Otherwise, exits in
        non-interactive mode or prompts the user continuously until a valid
        organisation UUID is provided in interactive mode.
        - org_name (str): The organisation name related to the validated
        organisation UUID.
        """

        user_orgs, _ = self.client.get_organisations()
        if not user_orgs:
            status_print(
                APP_WIZARD_MESSAGES["orgs_not_found"],
                status="error",
            )
            sys.exit(1)

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

    def get_plan_group(self, plan_group: str, org: str) -> tuple[str, str]:
        """
        Retrieves the plan group UUID from the user and validates it. Also
        retrieves the previously validated organisation UUID which is used to
        filter the available plan groups.

        Parameters:
        - plan_group (str): The plan group UUID provided by the user.
        - org (str): The validated organisation UUID.

        Returns:
        - plan_group (str): The plan group UUID, if valid. Otherwise, exits in
        non-interactive mode or prompts the user continuously until a valid
        plan group UUID is provided in interactive mode.
        - plan_group_name (str): The plan group name related to the validated
        plan group UUID.
        """

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

    def get_region(self, region: str, plan_group: str) -> tuple[str, str]:
        """
        Retrieves the region UUID from the user and validates it. Also
        retrieves the previously validated plan group UUID which is used to
        filter the available regions.

        Parameters:
        - region (str): The region UUID provided by the user.
        - plan_group (str): The validated plan group UUID.

        Returns:
        - region (str): The region UUID, if valid. Otherwise, exits in
        non-interactive mode or prompts the user continuously until a valid
        region UUID is provided in interactive mode.
        - region_name (str): The region name related to the validated
        region UUID.
        """

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

    def get_template(self, template: str) -> tuple[str | None, str | None]:
        """
        Retrieves the template URL from the user and validates it.

        Parameters:
        - template (str | None): The template URL provided by the user.

        Returns:
        - template (str | None): The template URL, if valid. Otherwise,
        exits in non-interactive mode or prompts the user continuously until a
        valid template URL is provided in interactive mode. If the user skips
        this step, returns None.
        - template_uuid (str | None): The template UUID related to the
        validated template URL. If the user skips this step or the template
        URL is custom (not a Divio template), returns None.
        """

        template_uuid = None
        divio_templates, _ = self.client.get_application_templates()
        divio_templates = {
            t["uuid"]: {
                "name": t["name"],
                "url": t["url"],
            }
            for t in divio_templates
        }

        if not self.interactive:
            if not template:
                return None, None

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

            for uuid in divio_templates:
                if divio_templates[uuid]["url"] == template:
                    template_uuid = uuid
                    break
        # Interactive mode
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
                return None, None
            # Divio template
            elif create_template == "select":
                divio_template_options = [
                    inquirer.List(
                        "uuid",
                        message=APP_WIZARD_MESSAGES["template_select"],
                        choices=[
                            (f"{divio_templates[uuid]['name']} ({uuid})", uuid)
                            for uuid in divio_templates
                        ],
                        carousel=True,
                    )
                ]
                template_uuid = inquirer.prompt(
                    divio_template_options, raise_keyboard_interrupt=True
                )["uuid"]
                template = divio_templates[template_uuid]["url"]
            # Custom template
            else:
                while True:
                    if not template:
                        template = prompt(
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
                        for uuid in divio_templates:
                            if divio_templates[uuid]["url"] == template:
                                template_uuid = uuid
                                break
                        break

        return template, template_uuid

    def get_template_release_commands(
        self, template_uuid: str | None
    ) -> list[dict] | None:
        """
        Retrieves the previously validated template UUID and uses it to
        retrieve the release commands related to that template.

        Parameters:
        - template_uuid (str | None): The application template UUID.

        Returns:
        - template_release_commands (list[dict] | None): The template release
        commands related to the application template UUID. In case of a custom
        or no template, returns None.
        """

        if template_uuid is None:
            return None

        return self.client.get_application_template(template_uuid)[
            "release_commands"
        ]

    def get_services(
        self, template_uuid: str | None, region: str
    ) -> list[dict] | None:
        """
        Retrieves the validated template UUID as well as the selected region
        and proceeds on retrieving the services related to that template, if
        any.

        NOTE: This method will be used in the future to attach user selected
        services as well.

        Parameters:
        - template_uuid (str | None): The template UUID.
        - region (str): The selected region UUID.

        Returns:
        - services (list[dict]): The services related to the selected template
        converted to the form retrieved from the corresponding services API
        listing endpoint, with the addition of the selected prefixes for each
        one. Those prefixes can be used later on to attach those services to
        any specific environment. If a custom template (not a Divio template)
        or no template was selected or the template did not include any
        services, returns None.
        """

        if template_uuid is None:
            # Will not apply when user selected services are implemented.
            return None

        template_services_config = self.client.get_application_template(
            template_uuid
        )["services"]

        # App templates include information about their required services in
        # the form of a list of dictionaries containing each service's
        # identifier and prefix. We need map these objects to the ones
        # retrieved from the actual services API endpoint and use the latter.
        # In addition, we need to inject the prefixes that will be used later
        # on to attach services to the application.
        template_services = []
        if template_services_config:
            region_services, _ = self.client.get_services(region_uuid=region)
            template_services_config_id_prefix_mapping = {
                s["id"]: s["prefix"] for s in template_services_config
            }

            for region_service in region_services:
                if (
                    region_service["identifier"]
                    in template_services_config_id_prefix_mapping
                ):
                    region_service[
                        "prefix"
                    ] = template_services_config_id_prefix_mapping[
                        region_service["identifier"]
                    ]
                    template_services.append(region_service)

        include_template_services = False
        if template_services and self.interactive:
            echo(APP_WIZARD_MESSAGES["detected_template_services"])

            echo(
                "\nTemplate services:\n"
                + "".join(
                    [
                        f"  {s['name']} ({s['uuid']})\n"
                        for s in template_services
                    ]
                )
            )

            include_template_services = confirm(
                APP_WIZARD_MESSAGES["include_template_services"],
                default=True,
            )

        return (
            template_services
            if include_template_services or not self.interactive
            else None
        )

    def get_release_commands(
        self, template_uuid: str | None
    ) -> list[dict] | None:
        """
        Retrieves the release commands from the user one by one and validates
        them. Also, retrieves any potential release commands included in the
        selected template and injects them into the release commands list.

        Parameters:
        - template_uuid (str | None): The template UUID from which to retrieve
        any potential release commands.

        Returns:
        - release_commands (list[dict]): The release commands provided by the
        user, including the ones that are potentially imported by a template.
        If no release commands are present, both by the user and the template,
        returns None.
        """

        template_release_commands = self.get_template_release_commands(
            template_uuid
        )

        include_template_release_commands = False
        if template_release_commands and self.interactive:
            echo(APP_WIZARD_MESSAGES["detected_template_release_commands"])

            echo(
                "\nTemplate release commands:\n"
                + "".join(
                    [
                        f"  {rc['label']}: {rc['command']}\n"
                        for rc in template_release_commands
                    ]
                )
            )

            include_template_release_commands = confirm(
                APP_WIZARD_MESSAGES["include_template_release_commands"],
                default=True,
            )

        release_commands = (
            template_release_commands
            if include_template_release_commands or not self.interactive
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
                    release_command_label = prompt(
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
                release_command_value = prompt(
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

        return release_commands or None

    def get_git_repo(
        self, org: str
    ) -> tuple[str | None, str | None, str | None]:
        """
        Retrieves the validated organisation UUID and proceeds on creating a
        repository related to that organisation. The created repository will
        be subjected to a verification process.

        If the verification process fails, the user will be prompted to
        restart, retry or skip the verification process. In any case, only a
        successful verification will allow this repository to be later
        connected to the application by providing all the required information
        (repository UUID and branch) during the application creation process.

        Parameters:
        - org (str): The validated organisation UUID.

        Returns:
        - repo_uuid (str | None): The repository UUID, if the verification
        process was successful. Otherwise, returns None.
        - repo_url (str | None): The repository URL, if the verification
        process was successful. Otherwise, returns None.
        - repo_branch (str | None): The repository branch, if the verification
        process was successful. Otherwise, returns None.
        """

        if not self.interactive:
            return None, None, None

        restart_connection = False
        suggested_repo_url = None
        suggested_repo_branch = "main"

        while True:
            if not (
                restart_connection
                or confirm(APP_WIZARD_MESSAGES["repo_connect"])
            ):
                return None, None, None
            else:
                # URL
                repo_url = get_repo_url(self.client, suggested_repo_url)

                # Branch
                repo_branch = prompt(
                    APP_WIZARD_MESSAGES["repo_branch_enter"],
                    default=suggested_repo_branch,
                )

                # URL scheme
                repo_url_parsed = parse(repo_url)
                auth_type = repo_url_parsed.scheme

                # SSH authentication
                if auth_type == "ssh":
                    # TODO: Retrieve available repository SSH key types
                    # dynamically, not as a hardcoded list.
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

                    response = self.client.create_repository(
                        org,
                        repo_url,
                        auth_type=auth_type,
                        ssh_key_type=repo_ssh_key_type,
                    )
                    repo_uuid = response["uuid"]

                    echo("SSH Key:")
                    secho(f"{response['auth_info']}\n", fg="green")
                    if confirm(
                        APP_WIZARD_MESSAGES["create_deploy_key"], default=True
                    ):
                        while True:
                            echo("Repository verification in progress...")
                            verification_status = verify_app_repo(
                                self.client,
                                repo_uuid,
                                repo_branch,
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

                            return repo_uuid, repo_url, repo_branch
                # Username/password authentication
                else:
                    host_username = prompt(
                        APP_WIZARD_MESSAGES["repo_host_username_enter"]
                    )
                    host_password = prompt(
                        APP_WIZARD_MESSAGES["repo_host_password_enter"],
                        hide_input=True,
                    )

                    response = self.client.create_repository(
                        org,
                        repo_url,
                        auth_type=auth_type,
                        host_username=host_username,
                        host_password=host_password,
                    )
                    repo_uuid = response["uuid"]

                    while True:
                        echo("Repository verification in progress...")
                        verification_status = verify_app_repo(
                            self.client,
                            repo_uuid,
                            repo_branch,
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

                        return repo_uuid, repo_url, repo_branch

    def create_app(
        self,
        data: dict,
        services: list[dict] | None = None,
        deploy: bool = False,
    ) -> None:
        """
        Creates an application using the provided data while takind care of
        displaying the application details in multiple formats depending on
        the verbosity level and the interactivity mode.

        Creates services to the application's test environment if the user
        requested such an action.

        Triggers the deployment of the application's test environment if the
        user requested such an action.

        Parameters:
        - data (dict): The application data.
        - services (list[dict] | None): The services to be attached to the
        application's test environment.
        - deploy (bool): Whether or not to trigger the deployment of the
        application's test environment.
        """

        # Application creation and details display.
        if not self.interactive:
            response = self.client.application_create(data=data)
            if self.verbose:
                app_details = app_details_summary(
                    data,
                    metadata=self.metadata,
                    deploy=deploy,
                    services=services,
                    as_json=self.as_json,
                )
                app_url = build_app_url(self.client, response["uuid"])

                if self.as_json:
                    app_details["app_url"] = app_url
                    echo(json.dumps(app_details, indent=4))
                else:
                    echo(f"Application Details\n{app_details}")
                    status_print(
                        f"Application created! Visit here: {app_url}",
                        status="success",
                    )
        else:
            if self.verbose:
                app_details = app_details_summary(
                    data,
                    metadata=self.metadata,
                    deploy=deploy,
                    services=services,
                    as_json=self.as_json,
                )

                echo("\nApplication Details")
                echo(
                    json.dumps(app_details, indent=4)
                    if self.as_json
                    else app_details
                )
                echo()

            if confirm(
                APP_WIZARD_MESSAGES["confirm_app_creation"],
                default=True,
            ):
                response = self.client.application_create(data=data)
            else:
                raise Abort

            if self.verbose:
                app_url = build_app_url(self.client, response["uuid"])
                status_print(
                    f"Application created! Visit here: {app_url}",
                    status="success",
                )

        if services or deploy:
            # The test environment UUID will only be needed later on in case
            # of a deploy request or the attachment of services. Not necessary
            # if neither of the two applies.
            app_envs = self.client.get_environments(
                params={"application": response["uuid"], "slug": "test"},
            )
            test_env_uuid = app_envs["results"][0]["uuid"]

        # Services
        if services:
            for service in services:
                self.client.add_service_instances(
                    environment_uuid=test_env_uuid,
                    prefix=service["prefix"].upper(),
                    region_uuid=data["region"],
                    service_uuid=service["uuid"],
                )

        # Deployment
        if deploy:
            # An automatic deployment request during app creation refers only
            # to the test environment for now.
            self.client.deploy_environment(test_env_uuid)
            if self.verbose and self.interactive:
                status_print(
                    APP_WIZARD_MESSAGES["deployment_triggered"],
                    status="success",
                )
