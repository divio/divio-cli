import click
import requests

from . import messages


class SingleHostSession(requests.Session):
    def __init__(self, host, **kwargs):
        super(SingleHostSession, self).__init__()
        self.host = host.rstrip('/')
        for key, value in kwargs.items():
            setattr(self, key, value)

    def request(self, method, url, *args, **kwargs):
        url = self.host + url
        return super(SingleHostSession, self).request(
            method, url, *args, **kwargs
        )


class APIRequest(object):
    network_exception_message = messages.NETWORK_ERROR_MESSAGE
    default_error_message = messages.SERVER_ERROR
    response_code_error_map = {
        requests.codes.forbidden: messages.AUTH_INVALID_TOKEN,
        requests.codes.not_found: messages.RESOURCE_NOT_FOUND,
    }

    method = 'GET'
    url = None

    def __init__(self, session, url_kwargs=None, data=None, files=None, *args, **kwargs):
        self.session = session
        self.url_kwargs = url_kwargs or {}
        self.data = data or {}
        self.files = files or {}

    def get_url(self):
        return self.url.format(**self.url_kwargs)

    def request(self, *args, **kwargs):
        try:
            response = self.session.request(
                self.method, self.get_url(),
                data=self.data, files=self.files,
                *args, **kwargs
            )
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            raise click.ClickException(messages.NETWORK_ERROR_MESSAGE)

        return self.process(response)

    def process(self, response):
        if not response.ok:
            error_msg = self.response_code_error_map.get(response.status_code)
            if not error_msg:
                error_msg = '{}\n\n{}'.format(
                    self.default_error_message,
                    response.content[:300],
                )
            raise click.ClickException(error_msg)

        return self.echo(response)

    def echo(self, response):
        return response.json()


class TextResponse(object):
    def echo(self, response):
        return response.text


class LoginRequest(APIRequest):
    default_error_message = messages.AUTH_SERVER_ERROR
    url = '/api/v1/login-with-token/'
    method = 'POST'


class ProjectListRequest(APIRequest):
    url = '/api/v1/user-websites/'


class ProjectDetailRequest(APIRequest):
    url = '/api/v1/website/{website_id}/info/'


class UploadAddonRequest(TextResponse, APIRequest):
    url = '/api/v1/apps/'
    method = 'POST'


class UploadBoilerplateRequest(TextResponse, APIRequest):
    url = '/api/v1/boilerplates/'
    method = 'POST'
