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
RESOURCE_NOT_FOUND = "Requested resource could not be found. Are you logged in?"
LOGIN_SUCCESSFUL = (
    u"Welcome to Divio Cloud. You are now logged in as {greeting}"
)
CONFIG_FILE_NOT_FOUND = u"Config file could not be not found at location: {}"
FILE_NOT_FOUND = u"File could not be found: {}"
INVALID_DB_SUBMITTED = (
    "The database dump you have uploaded contains an error. "
    "Please check the file 'db_upload.log' for errors and try again"
)
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
        "\nYou are about to push your local database to the {stage} server on ",
        "the Divio Cloud. This will replace ALL data on the Divio Cloud {stage} ",
        "server with the data you are about to push, including (but not limited to):",
        "  - User accounts",
        "  - CMS Pages & Plugins",
        "\nYou will also lose any changes that have been made on the {stage} ",
        "server since you pulled its database to your local environment. ",
        "\nIt is recommended to go the project settings on control.divio.com",
        "and take a backup before restoring the database. You can find this ",
        'action in the "Manage Project" section.',
        "\nPlease proceed with caution!",
    )
)

PUSH_MEDIA_WARNING = "\n".join(
    (
        "WARNING",
        "=======",
        "\nYou are about to push your local media files to the {stage} server on ",
        "the Divio Cloud. This will replace ALL existing media files with the ",
        "ones you are about to push.",
        "\nYou will also lose any changes that have been made on the {stage} ",
        "server since you pulled its files to your local environment. ",
        "\nIt is recommended to go the project settings on control.divio.com",
        "and take a backup before restoring media files. You can find this ",
        'action in the "Manage Project" section.',
        "\nPlease proceed with caution!",
    )
)
