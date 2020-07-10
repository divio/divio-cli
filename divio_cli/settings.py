import os

ACCESS_TOKEN_URL_PATH = "/account/desktop-app/access-token/"
BOILERPLATE_CONFIG_FILENAME = "boilerplate.json"
ADDON_CONFIG_FILENAME = "addon.json"
DOCKER_TEST_IMAGE = "busybox:1.30"
ALDRYN_DOT_FILE = ".aldryn"
DIVIO_DOT_FILE = ".divio/config.json"
DIVIO_GLOBAL_CONFIG_FILE = os.path.join(
    os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "divio/config.json"
)
