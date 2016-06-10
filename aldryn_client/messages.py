from __future__ import unicode_literals

SESSION_EXPIRED = 'Session expired. Please log in again.'
NETWORK_ERROR_MESSAGE = (
    'Network error. Please check your connection and try again.'
)
AUTH_SERVER_ERROR = (
    'A problem occured while trying to authenticate with aldryn.com. '
    'Please try again later'
)
SERVER_ERROR = (
    'A problem occured while trying to communicate with aldryn.com. '
    'Please try again later'
)
AUTH_INVALID_TOKEN = 'Login failed. Invalid token specified'
RESOURCE_NOT_FOUND = 'Requested resource could not be found'
LOGIN_SUCCESSFUL = 'Welcome to Aldryn. You are now logged in as {greeting}'
CONFIG_FILE_NOT_FOUND = 'Config file could not be not found at location: {}'
FILE_NOT_FOUND = 'File could not be found: {}'
INVALID_DB_SUBMITTED = (
    "The database dump you have uploaded contains an error. "
    "Please check the file 'db_upload.log' for errors and try again"
)
LOGIN_CHECK_SUCCESSFUL = (
    'Authentication with server successful. You are logged in.'
)
LOGIN_CHECK_ERROR = (
    'You are currently not logged in, '
    'please log in using `aldryn login`.'
)
