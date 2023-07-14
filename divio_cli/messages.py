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
    "enter_name": "Enter a name for your application",
    "enter_slug": "Enter a slug for your application",
    "enter_organisation": "Enter the UUID of the organisation you want to create the application for",
    "enter_region": "Enter the UUID of the region you want to create the application in",
    "enter_project_template": "Enter the URL of the project template you want to use",
    "enter_plan": "Enter the UUID of the application plan you want to use",
    "create_release_commands": "Do you want to create some release commands for your application?",
    "enter_release_command_name": "Enter a name for your release command",
    "enter_release_command_value": "Enter the value for your release command",
    "add_another_release_command": "Do you want to add another release command?",
    "connect_custom_repository": "Want to use a custom repository for your application instead of the default one hosted by Divio?",
    "enter_repository_url": "Enter the URL of the repository you want to use",
    "enter_repository_default_branch": "Enter the name of the default branch you want to use",
    "enter_repository_access_key_type": "Enter the type of access key you want to use for your repository",
    "create_deploy_key": "Please register this ssh key with your repository provider. Ready to continue?",
    "repository_verification_timeout": "Repository verification timed out. Please try again later.",
}
