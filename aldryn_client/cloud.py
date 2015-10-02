import os
from netrc import netrc
from urlparse import urlparse

import click

from . import settings
from . import messages
from . import api_requests
from .utils import create_temp_dir


ENDPOINT = 'https://control.{host}'
DEFAULT_HOST = 'aldryn.com'


def get_aldryn_host():
    return os.environ.get('ALDRYN_HOST', DEFAULT_HOST)


def get_endpoint(host=None):
    target_host = host or get_aldryn_host()
    endpoint = ENDPOINT.format(host=target_host)
    if target_host != DEFAULT_HOST:
        endpoint_warning = 'Warning: Using custom endpoint {}'.format(endpoint)
        underline = '-' * len(endpoint_warning)
        click.secho(
            os.linesep.join((endpoint_warning, underline, '')),
            fg='yellow',
        )
    return endpoint


class CloudClient(object):
    def __init__(self, host=None):
        self.endpoint = get_endpoint(host)
        self.netrc = WritableNetRC()
        self.session = self.init_session()

    # Helpers
    def get_auth_header(self):
        host = urlparse(self.endpoint).hostname
        data = self.netrc.hosts.get(host)
        if data:
            return {'Authorization': 'Basic {}'.format(data[2])}
        return {}

    def get_access_token_url(self):
        return '{}/{}'.format(
            self.endpoint.rstrip('/'),
            settings.ACCESS_TOKEN_URL_PATH.lstrip('/')
        )

    def init_session(self):
        return api_requests.SingleHostSession(
            self.endpoint,
            headers=self.get_auth_header(),
            trust_env=False
        )

    def authenticate(self, token):
        self.session.headers['Authorization'] = 'Basic {}'.format(token)

    def login(self, token):
        request = api_requests.LoginRequest(
            self.session,
            data={'token': token}
        )
        user_data = request()

        self.authenticate(token)

        first_name = user_data.get('first_name')
        last_name = user_data.get('last_name')
        email = user_data.get('email')

        if first_name and last_name:
            greeting = '{} {} ({})'.format(first_name, last_name, email)
        elif first_name:
            greeting = '{} ({})'.format(first_name, email)
        else:
            greeting = email

        self.netrc.add(urlparse(self.endpoint).hostname, email, None, token)
        self.netrc.write()

        return messages.LOGIN_SUCCESSFUL.format(greeting=greeting)

    def get_projects(self):
        request = api_requests.ProjectListRequest(self.session)
        return request()

    def get_project(self, website_id):
        request = api_requests.ProjectDetailRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def is_project_locked(self, website_id):
        request = api_requests.ProjectLockQueryRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def lock_project(self, website_id):
        request = api_requests.ProjectLockRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def unlock_project(self, website_id):
        request = api_requests.ProjectUnlockRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def upload_addon(self, archive_obj):
        request = api_requests.UploadAddonRequest(
            self.session,
            files={'app': archive_obj}
        )
        return request()

    def upload_boilerplate(self, archive_obj):
        request = api_requests.UploadBoilerplateRequest(
            self.session,
            files={'boilerplate': archive_obj}
        )
        return request()

    def get_website_id_for_slug(self, slug):
        request = api_requests.SlugToIDRequest(
            self.session,
            url_kwargs={'website_slug': slug}
        )
        return request()

    def get_website_slug_for_id(self, website_id):
        request = api_requests.IDToSlugRequest(
            self.session,
            url_kwargs={'website_id': website_id}
        )
        return request()

    def download_db(self, website_slug, filename=None, directory=None):
        request = api_requests.DownloadDBRequest(
            self.session,
            url_kwargs={'website_slug': website_slug},
        )
        dump_path = os.path.join(
            directory or create_temp_dir(),
            filename or 'db_dump.tar.gz',
        )

        response = request()
        with open(dump_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
        return dump_path


class WritableNetRC(netrc):
    def __init__(self, *args, **kwargs):
        netrc_path = self.get_netrc_path()
        if not os.path.exists(netrc_path):
            open(netrc_path, 'a').close()
            os.chmod(netrc_path, 0600)
        netrc.__init__(self, *args, **kwargs)

    def get_netrc_path(self):
        # netrc uses os.environ['HOME'], which isn't defined on Windows
        home = os.environ['HOME'] = os.path.expanduser('~')
        return os.path.join(home, '.netrc')

    def add(self, host, login, account, password):
        self.hosts[host] = (login, account, password)

    def remove(self, host):
        if host in self.hosts:
            del self.hosts[host]

    def write(self, path=None):
        if path is None:
            path = self.get_netrc_path()

        out = []
        for machine, data in self.hosts.items():
            login, account, password = data
            out.append('machine {}'.format(machine))
            if login:
                out.append('\tlogin {}'.format(login))
            if account:
                out.append('\taccount {}'.format(account))
            if password:
                out.append('\tpassword {}'.format(password))

        with open(path, 'w') as f:
            f.write(os.linesep.join(out))
