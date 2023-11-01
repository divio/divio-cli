import json
import logging
import os
import pprint
import textwrap
from urllib.parse import urljoin

from requests import Session

from divio_cli.config import WritableNetRC
from divio_cli.exceptions import DivioException


DEFAULT_ZONE = "divio.com"

ACCESS_TOKEN_URL_PATH = "/account/desktop-app/access-token/"
GET_CURRENT_USER_URL_PATH = "/iam/v3/me/"

logger = logging.getLogger("divio.client")
http_request_logger = logging.getLogger("divio.client.http.request")
http_response_logger = logging.getLogger("divio.client.http.response")

http_response_body_logger = logging.getLogger(
    "divio.client.http.response-body",
)


class ApiError(DivioException):
    def __init__(self, *args, status_code=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.status_code = status_code


class Client:
    def __init__(self, token="", zone=DEFAULT_ZONE):
        self.zone = zone

        self.token = ""
        self.session = None
        self.headers = {}
        self.user_info = {}

        if token:
            self.authenticate(token=token)

    def __repr__(self):
        return f"<divio.Client(user={self.get_user_name()!r}, zone={self.zone!r})>"

    # HTTP requests
    def get_api_host(self):
        return f"api.{self.zone}"

    def get_control_panel_host(self):
        return f"control.{self.zone}"

    def get_api_url(self, path):
        return urljoin(f"https://{self.get_api_host()}", path)

    def get_control_panel_url(self, path, **query):
        return urljoin(f"https://{self.get_control_panel_host()}", path)

    def request(self, method, path, *args, **kwargs):
        url = self.get_api_url(path=path)

        http_request_logger.debug("%s %s", method, url)

        response = self.session.request(
            method=method,
            url=url,
            headers=self.headers,
            *args,  # NOQA: B026
            **kwargs,
        )

        http_response_logger.debug(
            "url=%s, status-code=%s, content-type=%s, content-length=%s",
            response.url,
            response.status_code,
            response.headers.get("content-type", "[NOTSET]"),
            response.headers.get("content-length", "[NOTSET]"),
        )

        try:
            text = response.json()

        except json.JSONDecodeError:
            text = response.text

        http_response_body_logger.debug(
            "url=%s \n%s",
            response.url,
            textwrap.indent(
                text=pprint.pformat(text),
                prefix="    ",
            ),
        )

        if response.status_code != 200:
            raise ApiError(status_code=response.status_code)

        return response

    def get_json(self, *args, **kwargs):
        response = self.request(*args, **kwargs)

        try:
            return response.json()

        except json.JSONDecodeError as exception:
            raise RuntimeError("invalid response") from exception

    def get_access_token_url(self):
        return self.get_control_panel_url(path=ACCESS_TOKEN_URL_PATH)

    # session management
    def get_session(self):
        session = Session()

        session.proxies = {
            "http": os.environ.get("HTTP_PROXY", ""),
            "https": os.environ.get("HTTPS_PROXY", ""),
        }

        session.trust_env = False

        return session

    def pull_user_info(self):
        logger.debug("pulling user information")

        self.user_info.clear()

        response = self.request(
            method="GET",
            path=GET_CURRENT_USER_URL_PATH,
        )

        if response.status_code == 200:
            self.user_info.update(**response.json())

        return response.status_code == 200

    def authenticate(self, token="__netrc__"):
        logger.debug("trying to authenticate")

        # FIXME: the API host would make more sense here but for compatibility
        # reasons the control-panel host has to be used
        # TODO: remove after the cloud-client was removed
        host = self.get_control_panel_host()

        # reset session
        self.headers.clear()
        self.session = self.get_session()

        # set auth token
        self.token = token

        if self.token == "__netrc__":
            logger.debug("reading %s", WritableNetRC.get_netrc_path())

            netrc = WritableNetRC()

            if host not in netrc.hosts:
                raise DivioException(
                    f"{host} not found in {netrc.get_netrc_path()}",
                )

            self.token = netrc.hosts[host][2]

        self.headers["Authorization"] = f"Token {self.token}"

        # check auth token
        authenticated = self.pull_user_info()

        if authenticated:
            logger.debug("authenticated as %s", self.user_info["email"])

        else:
            logger.debug("authentication failed")

        return authenticated

    def is_authenticated(self):
        return bool(self.user_info)

    # user helper
    def get_user_email(self):
        return self.user_info["email"]

    def get_user_name(self):
        first_name = self.user_info.get("first_name", "Anonymous")
        last_name = self.user_info.get("last_name", "")
        email = self.user_info.get("email", "")

        if email:
            email = f"<{email}>"

        strings = [first_name, last_name, email]

        return " ".join([string for string in strings if string])
