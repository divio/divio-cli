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
    "You are currently not logged in, please log in using `divio login`."
)

LOGOUT_CONFIRMATION = "Are you sure you want to logout from {}?"
LOGOUT_ERROR = "You are not logged into {} at the moment"
LOGOUT_SUCCESS = "Logged out from {}"

PUSH_DB_WARNING = (
    "\nWARNING"
    "\n======="
    "\n\nYou are about to push your local database to the {environment} environment on"
    "\nthe Divio Cloud. This will replace ALL data on the Divio Cloud {environment}"
    "\nenvironment with the data you are about to push, including (but not limited to):"
    "\n  - User accounts"
    "\n  - CMS Pages & Plugins"
    "\n\nYou will also lose any changes that have been made on the {environment}"
    "\nenvironment since you pulled its database to your local environment."
    "\n\nIt is recommended to go the backup section on control.divio.com"
    "\nand take a backup before restoring the database."
    "\nPlease proceed with caution!"
)


PUSH_MEDIA_WARNING = (
    "\nWARNING"
    "\n======="
    "\n\nYou are about to push your local media files to the {environment} environment on"
    "\nthe Divio Cloud. This will replace ALL existing media files with the"
    "\nones you are about to push."
    "\n\nYou will also lose any changes that have been made on the {environment}"
    "\nenvironment since you pulled its files to your local environment."
    "\n\nIt is recommended to go the backup section on control.divio.com"
    "\nand take a backup before restoring media files."
    "\n\nPlease proceed with caution!"
)
