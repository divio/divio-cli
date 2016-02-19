import os
from netrc import netrc
from time import sleep

import click
from six.moves.urllib_parse import urlparse

from . import settings
from . import messages
from . import api_requests
from .config import Config


ENDPOINT = 'https://control.{host}'
DEFAULT_HOST = 'aldryn.com'


def is_http_url(url):
    return url.startswith('http://') or url.startswith('https://')


def get_aldryn_host():
    host = os.environ.get('ALDRYN_HOST', DEFAULT_HOST)

    # check for aldryn-client v1 syntax
    if is_http_url(host):
        old_style = host
        proto, domain = host.split('://')
        parts = domain.split('.')
        host = '.'.join(parts[-3:])
        click.secho(
            'You are using old ALDRYN_HOST syntax. Please change {} to {}'
            .format(old_style, host),
            fg='yellow'
        )

    return host


def get_endpoint(host=None):
    if host and is_http_url(host):
        return host
    target_host = host or get_aldryn_host()
    endpoint = ENDPOINT.format(host=target_host)
    if target_host != DEFAULT_HOST:
        click.secho('Using custom endpoint {}\n'.format(endpoint), fg='yellow')
    return endpoint


class CloudClient(object):
    def __init__(self, host=None):
        self.config = Config()
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

    def deploy_project_or_get_progress(self, website_id, stage):
        def fmt_progress(data):
            if not data:
                return 'Connecting to remote'
            return '{} ({})'.format(
                data['verbose_state'],
                data['heartbeat_ago_formatted']
            )

        response = self.deploy_project_progress(website_id, stage)
        if response['is_deploying']:
            click.secho(
                'Already deploying {} server, attaching to running '
                'deployment'.format(stage),
                fg='yellow'
            )
        else:
            click.secho('Deploying {} server'.format(stage), fg='green')
            self.deploy_project(website_id, stage)
            sleep(1)
            response = self.deploy_project_progress(website_id, stage)
        try:
            with click.progressbar(
                    length=100, show_percent=True,
                    show_eta=False, item_show_func=fmt_progress) as bar:
                while response['is_deploying']:
                    response = self.deploy_project_progress(website_id, stage)
                    bar.current_item = progress = response['deploy_progress']
                    bar.update(
                        # update the difference of the current percentage
                        # to the new percentage
                        progress['main_percent'] +
                        progress['extra_percent'] -
                        bar.pos
                    )
                    sleep(3)
        except KeyboardInterrupt:
            click.secho('Disconnected')

    def deploy_project_progress(self, website_id, stage):
        request = api_requests.DeployProjectProgressRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        data = request()
        return data[stage]

    def deploy_project(self, website_id, stage):
        request = api_requests.DeployProjectRequest(
            self.session,
            url_kwargs={'website_id': website_id},
            data={'stage': stage}
        )
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

    def register_addon(self, package_name, verbose_name, organisation_id=None):
        request = api_requests.RegisterAddonRequest(
            self.session,
            data={
                'package_name': package_name,
                'name': verbose_name,
                'organisation': organisation_id,
            }
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

    def download_backup(self, website_slug, filename=None, directory=None):
        request = api_requests.DownloadBackupRequest(
            self.session,
            url_kwargs={'website_slug': website_slug},
            filename=filename,
            directory=directory,
        )
        return request()

    def download_db_request(self, website_id):
        request = api_requests.DownloadDBRequestRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def download_db_progress(self, url):
        request = api_requests.DownloadDBProgressRequest(
            self.session,
            url=url,
        )
        return request()

    def download_db(self, website_slug, url=None, filename=None, directory=None):
        request = api_requests.DownloadDBRequest(
            self.session,
            url=url,
            url_kwargs={'website_slug': website_slug},
            filename=filename,
            directory=directory,
        )
        return request()

    def download_media_request(self, website_id):
        request = api_requests.DownloadMediaRequestRequest(
            self.session,
            url_kwargs={'website_id': website_id},
        )
        return request()

    def download_media_progress(self, url):
        request = api_requests.DownloadMediaProgressRequest(
            self.session,
            url=url,
        )
        return request()

    def download_media(self, website_slug, url=None,
                       filename=None, directory=None):
        request = api_requests.DownloadMediaRequest(
            self.session,
            url=url,
            url_kwargs={'website_slug': website_slug},
            filename=filename,
            directory=directory,
        )
        return request()

    def upload_db(self, website_id, archive_path):
        request = api_requests.UploadDBRequest(
            self.session,
            url_kwargs={'website_id': website_id},
            files={'db_dump': open(archive_path, 'rb')}
        )
        return request()

    def upload_db_progress(self, url):
        request = api_requests.UploadDBProgressRequest(
            self.session,
            url=url,
        )
        return request()

    def upload_media(self, website_id, archive_path):
        request = api_requests.UploadMediaFilesRequest(
            self.session,
            url_kwargs={'website_id': website_id},
            files={'media_files': open(archive_path, 'rb')}
        )
        return request()

    def upload_media_progress(self, url):
        request = api_requests.UploadMediaFilesProgressRequest(
            self.session,
            url=url,
        )
        return request()


class WritableNetRC(netrc):
    def __init__(self, *args, **kwargs):
        netrc_path = self.get_netrc_path()
        if not os.path.exists(netrc_path):
            open(netrc_path, 'a').close()
            os.chmod(netrc_path, 0o600)
        kwargs['file'] = netrc_path
        try:
            netrc.__init__(self, *args, **kwargs)
        except IOError:
            raise click.ClickException(
                "Please make sure your netrc config file ('{}') can be read "
                "and written by the current user."
                .format(netrc_path)
            )

    def get_netrc_path(self):
        """
        netrc uses os.environ['HOME'] for path detection which is
        not defined on Windows. Detecting the correct path ourselves
        """
        home = os.path.expanduser('~')
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
