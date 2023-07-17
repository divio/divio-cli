SESSION_EXPIRED = "Session expired. Please log in again."
NETWORK_ERROR_MESSAGE = (
    "Network error. Please check your connection and try again."
)
AUTH_SERVER_ERROR = (
    "A problem occured while trying to authenticate with divio.com. "
    "Please try again later"
)
SERVER_ERROR = (
    "A problem occured while trying to communicate with divio.com. "
    "Please try again later"
)
AUTH_INVALID_TOKEN = "Login failed. Invalid token specified"
RESOURCE_NOT_FOUND_ANONYMOUS = "Resource not found"
RESOURCE_NOT_FOUND = "Resource not found. You are logged in as '{login}', please check if you have permissions to access the resource"
LOGIN_SUCCESSFUL = (
    "Welcome to Divio Cloud. You are now logged in as {greeting}"
)
CONFIG_FILE_NOT_FOUND = "Config file could not be not found at location: {}"
FILE_NOT_FOUND = "File could not be found: {}"
BAD_REQUEST = "Request could not be processed"
LOGIN_CHECK_SUCCESSFUL = (
    "Authentication with server successful. You are logged in."
)
LOGIN_CHECK_ERROR = (
    "You are currently not logged in, " "please log in using `divio login`."
)

PUSH_DB_WARNING = "\n".join(
    (
        "WARNING",
        "=======",
        "\nYou are about to push your local database to the {environment} environment on ",
        "the Divio Cloud. This will replace ALL data on the Divio Cloud {environment} ",
        "environment with the data you are about to push, including (but not limited to):",
        "  - User accounts",
        "  - CMS Pages & Plugins",
        "\nYou will also lose any changes that have been made on the {environment} ",
        "environment since you pulled its database to your local environment. ",
        "\nIt is recommended to go the backup section on control.divio.com",
        "and take a backup before restoring the database.",
        "\nPlease proceed with caution!",
    )
)

PUSH_MEDIA_WARNING = "\n".join(
    (
        "WARNING",
        "=======",
        "\nYou are about to push your local media files to the {environment} environment on ",
        "the Divio Cloud. This will replace ALL existing media files with the ",
        "ones you are about to push.",
        "\nYou will also lose any changes that have been made on the {environment} ",
        "environment since you pulled its files to your local environment. ",
        "\nIt is recommended to go the backup section on control.divio.com",
        "and take a backup before restoring media files.",
        "\nPlease proceed with caution!",
    )
)


CREATE_APP_WIZARD_MESSAGES = {
    "enter_application_name": "Enter the name of your application",
    "enter_application_slug": "Enter the slug of your application",
    "application_name_already_exists": "An application with this name already exists. Please try again.",
    "application_slug_already_exists": "An application with this slug already exists. Please try again.",
    "invalid_application_slug": "Invalid slug. It must contain only lowercase letters, numbers and hyphens. Please try again.",
    "enter_organisation": "Enter the UUID of your organization",
    "invalid_organisation": "Invalid organization. Please try again.",
    "enter_region": "Enter the UUID of your region",
    "invalid_region": "Invalid region. Please try again.",
    "enter_project_template": "Enter the URL of the project template",
    "invalid_project_template_url": "Invalid project template URL. Please try again.",
    "enter_plan": "Enter the UUID of your application plan",
    "invalid_plan": "Invalid plan. Please try again.",
    "create_release_commands": "Want to create release commands for your application?",
    "enter_release_command_name": "Enter the name of your release command",
    "enter_release_command_value": "Enter the value of your release command",
    "add_another_release_command": "Want to add another release command?",
    "connect_custom_repository": "Want to use a custom repository for your application?",
    "enter_repository_url": "Enter the URL of your custom repository",
    "enter_repository_default_branch": "Enter the name of your target branch",
    "enter_repository_access_key_type": "Enter the type of your deploy key",
    "create_deploy_key": "Please register this ssh key with your repository provider. Otherwise, the repository verification will fail. Ready to continue?",
    "repository_verification_timeout": "Repository verification timed out. If this step is not completed, a default repository hosted on Divio Cloud will be used. Wanna try again?",
}
