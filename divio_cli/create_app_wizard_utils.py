import sys
import time

import click
import inquirer

from .utils import is_valid_url, table


CREATE_APP_WIZARD_MESSAGES = {
    # Name
    "enter_application_name": "Enter the name of your application",
    # Slug
    "enter_application_slug": "Enter the slug of your application",
    # Organisation
    "enter_organisation": "Enter the UUID of your organization",
    "invalid_organisation": "ERROR: Invalid organization UUID.",
    # Plan
    "enter_plan": "Enter the UUID of your application plan",
    "invalid_plan": "ERROR: Invalid plan UUID.",
    # Region
    "enter_region": "Enter the UUID of your region",
    "invalid_region": "ERROR: Invalid region UUID.",
    # Template
    "enter_project_template": "Enter the URL of the project template",
    "invalid_project_template_url": "ERROR: Invalid project template URL.",
    # Release commands
    "create_release_commands": "Want to create release commands for your application?",
    "enter_release_command_name": "Enter the name of your release command",
    "enter_release_command_value": "Enter the value of your release command",
    "add_another_release_command": "Want to add another release command?",
    # Custom repository
    "connect_custom_repository": "Want to use a custom repository for your application?",
    "enter_repository_url": "Enter the URL of your custom repository",
    "enter_repository_default_branch": "Enter the name of your target branch",
    "enter_repository_access_key_type": "Enter the type of your deploy key",
    "create_deploy_key": (
        "Please register this ssh key with your repository provider. "
        "Otherwise, the repository verification will fail. Ready to continue?"
    ),
    "repository_verification_timeout": (
        "Repository verification timed out. If this step is not completed, "
        "a default repository hosted on Divio Cloud will be used. Wanna try again?"
    ),
}


def validate_application_name(obj, name, interactive, verbose):
    while True:
        if not name:
            name = click.prompt(
                CREATE_APP_WIZARD_MESSAGES["enter_application_name"]
            )

        response = obj.client.validate_application_name(name)
        validated_name_data = response.get("name")

        if validated_name_data != name:
            for error in validated_name_data:
                click.secho(f"ERROR: {error}", fg="red")
            if interactive:
                name = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    f"SUCCESS: Accepted {name!r} as the name of the application.",
                    fg="green",
                )
            return name


def validate_application_slug(obj, slug, interactive, verbose):
    while True:
        if not slug:
            slug = click.prompt(
                CREATE_APP_WIZARD_MESSAGES["enter_application_slug"]
            )

        response = obj.client.validate_application_slug(slug)
        validated_slug_data = response.get("slug")

        if validated_slug_data != slug:
            for error in validated_slug_data:
                click.secho(f"ERROR: {error}", fg="red")
            if interactive:
                slug = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    f"SUCCESS: Accepted {slug!r} as the slug of the application.",
                    fg="green",
                )
            return slug


def validate_application_organisation(obj, organisation, interactive, verbose):
    available_organisations, _ = obj.client.get_organisations()
    organisations_uuid_name_mapping = {
        org["uuid"]: org["name"] for org in available_organisations
    }

    while True:
        if not organisation:
            options = [
                inquirer.List(
                    "uuid",
                    message=CREATE_APP_WIZARD_MESSAGES["enter_organisation"],
                    choices=[
                        (org["name"], org["uuid"])
                        for org in available_organisations
                    ],
                )
            ]
            organisation = inquirer.prompt(options)["uuid"]
            organisation_name = organisations_uuid_name_mapping[organisation]

        if organisation not in organisations_uuid_name_mapping.keys():
            click.secho(
                CREATE_APP_WIZARD_MESSAGES["invalid_organisation"], fg="red"
            )
            if interactive:
                organisation = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    (
                        f"SUCCESS: Accepted {organisation_name!r} "
                        f"as the organisation of the application."
                    ),
                    fg="green",
                )
            return organisation


def validate_application_plan(
    obj, plan, organisation_uuid, interactive, verbose
):

    plan_groups = obj.client.get_application_plan_groups_v2()["results"]
    plans = obj.client.get_application_plans_v2(organisation_uuid)["results"]

    valid_plan_group_uuids = [p["group_uuid"] for p in plans]

    available_plan_groups = [
        g for g in plan_groups if g["uuid"] in valid_plan_group_uuids
    ]
    plan_groups_uuid_name_mapping = {
        group["uuid"]: group["name"] for group in available_plan_groups
    }

    while True:
        if not plan:
            options = [
                inquirer.List(
                    "uuid",
                    message=CREATE_APP_WIZARD_MESSAGES["enter_plan"],
                    choices=[
                        (org["name"], org["uuid"])
                        for org in available_plan_groups
                    ],
                )
            ]
            plan = inquirer.prompt(options)["uuid"]
            plan_name = plan_groups_uuid_name_mapping[plan]

        if plan not in valid_plan_group_uuids:
            click.secho(CREATE_APP_WIZARD_MESSAGES["invalid_plan"], fg="red")
            if interactive:
                plan = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    (
                        f"SUCCESS: Accepted {plan_name!r} "
                        "as the plan of the application."
                    ),
                    fg="green",
                )

            # TODO: Return the plan ID for now.
            # To be removed once the API is updated.
            for p in available_plan_groups:
                if p["uuid"] == plan:
                    plan_id = p["id"]

            return plan, plan_id


def validate_application_region(
    obj, region, plan, plan_id, interactive, verbose
):
    available_regions_uuids = obj.client.get_application_plan_group_v2(
        plan_id
    )["regions_uuids"]

    available_regions, _ = obj.client.get_regions(
        params={"uuid": available_regions_uuids}
    )

    regions_uuid_name_mapping = {
        region["uuid"]: region["name"] for region in available_regions
    }

    while True:
        if not region:
            options = [
                inquirer.List(
                    "uuid",
                    message=CREATE_APP_WIZARD_MESSAGES["enter_region"],
                    choices=[
                        (org["name"], org["uuid"]) for org in available_regions
                    ],
                )
            ]

            region = inquirer.prompt(options)["uuid"]
            region_name = regions_uuid_name_mapping[region]

        if region not in regions_uuid_name_mapping.keys():
            click.secho(CREATE_APP_WIZARD_MESSAGES["invalid_region"], fg="red")
            if interactive:
                region = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    (
                        f"SUCCESS: Accepted {region_name!r} "
                        "as the region of the application."
                    ),
                    fg="green",
                )
            return region


def validate_application_template(obj, template, interactive, verbose):
    while True:
        if not template:
            template = click.prompt(
                CREATE_APP_WIZARD_MESSAGES["enter_project_template"]
            )

        if not is_valid_url(template):
            click.secho(
                CREATE_APP_WIZARD_MESSAGES["invalid_project_template_url"],
                fg="red",
            )
            if interactive:
                template = None
            else:
                sys.exit(1)
        else:
            if verbose:
                click.secho(
                    (
                        f"SUCCESS: Accepted {template!r} "
                        "as the template of the application."
                    ),
                    fg="green",
                )
            return template


def get_application_release_commands(verbose):
    release_commands = []
    if click.confirm(CREATE_APP_WIZARD_MESSAGES["create_release_commands"]):
        add_another_release_command = True
        while add_another_release_command:
            release_command_name = click.prompt(
                CREATE_APP_WIZARD_MESSAGES["enter_release_command_name"]
            )
            release_command_value = click.prompt(
                CREATE_APP_WIZARD_MESSAGES["enter_release_command_value"]
            )
            release_commands.append(
                {
                    "name": release_command_name,
                    "command": release_command_value,
                }
            )
            add_another_release_command = click.confirm(
                CREATE_APP_WIZARD_MESSAGES["add_another_release_command"]
            )

    if release_commands and verbose:
        release_commands_table = table(
            [[rc["name"], rc["command"]] for rc in release_commands],
            ["Name", "Command"],
            tablefmt="grid",
            maxcolwidths=50,
        )
        click.secho(
            "SUCCESS: Accepted the following release commands:", fg="green"
        )
        click.secho(release_commands_table, fg="yellow")

    return release_commands


def get_application_custom_git_repo(obj, organisation, verbose):
    if click.confirm(CREATE_APP_WIZARD_MESSAGES["connect_custom_repository"]):

        # All of those first 3 parameters can be validated the same way
        # as an application name, slug etc. Create a custom endpoint for
        # validating the fields of a repository.
        repository_url = click.prompt(
            CREATE_APP_WIZARD_MESSAGES["enter_repository_url"]
        )

        repository_default_branch = click.prompt(
            CREATE_APP_WIZARD_MESSAGES["enter_repository_default_branch"],
            default="main",
        )

        repository_key_type = click.prompt(
            CREATE_APP_WIZARD_MESSAGES["enter_repository_access_key_type"],
            default="ED25519",
        )

        # Create and validate the repository.
        response = obj.client.create_repository(
            organisation, repository_url, repository_key_type
        )
        repository_uuid = response["uuid"]
        repository_ssh_key = response["auth_info"]

        # Ask the user to add the ssh public key (deploy key) to the
        # repository provider.
        click.secho(f"SSH Key: {repository_ssh_key}", fg="green")
        click.confirm(CREATE_APP_WIZARD_MESSAGES["create_deploy_key"])

        # Verify the repository.
        c = 0
        response = obj.client.check_repository(
            repository_uuid, repository_default_branch
        )

        while response["code"] == "waiting" and c < 5:
            time.sleep(5)
            response = obj.client.check_repository(
                repository_uuid, repository_default_branch
            )
            c += 1

        if response["code"] == "waiting":
            click.secho(
                CREATE_APP_WIZARD_MESSAGES["repository_verification_timeout"],
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
            if verbose:
                click.secho("SUCCESS: Accepted custom repository.", fg="green")
            git_repo = {
                "uuid": repository_uuid,
                "default_branch": repository_default_branch,
            }

        return git_repo

    return None
