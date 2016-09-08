import subprocess
import platform
import tarfile
import tempfile

import os
import sys
from subprocess import CalledProcessError
from contextlib import contextmanager
from distutils.version import StrictVersion
from math import log

import click
import requests
from tabulate import tabulate
from six.moves.urllib_parse import urljoin

from . import __version__


ALDRYN_DEFUALT_BRANCH_NAME = "develop"


def hr(char='-', width=None, **kwargs):
    if width is None:
        width = click.get_terminal_size()[0]
    click.secho(char * width, **kwargs)


def table(data, headers):
    return tabulate(data, headers)


def indent(text, spaces=4):
    return '\n'.join(' ' * spaces + ln for ln in text.splitlines())


def get_package_version(path):
    return check_output(
            ['python', 'setup.py', '--version'],
            cwd=path
    ).strip()


@contextmanager
def dev_null():
    with open(os.devnull, 'wb') as devnull:
        yield devnull


@contextmanager
def silence_stderr():
    with dev_null() as devnull:
        with redirect_stderr(devnull):
            yield


@contextmanager
def silence_stdout():
    with dev_null() as devnull:
        with redirect_stdout(devnull):
            yield


@contextmanager
def redirect_stdout(new_stream):
    original_stream = sys.stdout
    sys.stdout = new_stream
    try:
        yield
    finally:
        sys.stdout = original_stream


@contextmanager
def redirect_stderr(new_stream):
    original_stream = sys.stderr
    sys.stderr = new_stream
    try:
        yield
    finally:
        sys.stderr = original_stream


def create_temp_dir():
    return tempfile.mkdtemp(prefix='tmp_aldryn_client_')


def tar_add_stringio(tar, string_io, name):
    info = tarfile.TarInfo(name=name)
    string_io.seek(0, os.SEEK_END)
    info.size = string_io.tell()
    string_io.seek(0)
    tar.addfile(tarinfo=info, fileobj=string_io)


def execute(func, *popenargs, **kwargs):
    catch = kwargs.pop('catch', True)
    if kwargs.pop('silent', False):
        if 'stdout' not in kwargs:
            kwargs['stdout'] = open(os.devnull, 'w')
            if not is_windows():
                # close file descriptor devnull after exit
                # unfortunately, close_fds is not supported on Windows
                # platforms if you redirect stdin/stdout/stderr
                # => http://svn.python.org/projects/python/
                #    branches/py3k/Lib/subprocess.py
                kwargs['close_fds'] = True
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.STDOUT
    try:
        return func(*popenargs, **kwargs)
    except subprocess.CalledProcessError as exc:
        if not catch:
            raise
        output = (
            'There was an error trying to run a command. This is most likely',
            'not an issue with aldryn-client, but the called program itself.',
            'Try checking the output of the command above.',
            'The command was:',
            '  {command}'.format(command=' '.join(exc.cmd))
        )
        hr(fg='red')
        click.secho(os.linesep.join(output), fg='red')
        sys.exit(1)


def check_call(*popenargs, **kwargs):
    return execute(subprocess.check_call, *popenargs, **kwargs)


def check_output(*popenargs, **kwargs):
    return execute(subprocess.check_output, *popenargs, **kwargs).decode()


def open_project_cloud_site(client, stage):
    from .localdev.utils import get_aldryn_project_settings

    assert stage in ('test', 'live')
    project_settings = get_aldryn_project_settings()
    project_data = client.get_project(project_settings['id'])
    url = project_data['{}_status'.format(stage)]['site_url']
    if url:
        click.launch(url)
    else:
        click.secho('No {} server deployed yet.'.format(stage), fg='yellow')


def get_dashboard_url(client):
    from .localdev.utils import get_aldryn_project_settings

    project_settings = get_aldryn_project_settings()
    project_data = client.get_project(project_settings['id'])
    return project_data['dashboard_url']


def get_project_cheatsheet_url(client):
    dashboard = get_dashboard_url(client)
    return urljoin(dashboard, 'local-development/')


def is_windows():
    return sys.platform == 'win32'


def is_linux():
    return sys.platform.startswith('linux')


unit_list = list(zip(
        ['bytes', 'kB', 'MB', 'GB', 'TB', 'PB'],
        [0, 0, 1, 2, 2, 2],
))


def pretty_size(num):
    """Human friendly file size"""
    # http://stackoverflow.com/a/10171475
    if num > 1:
        exponent = min(int(log(num, 1024)), len(unit_list) - 1)
        quotient = float(num) / 1024 ** exponent
        unit, num_decimals = unit_list[exponent]
        format_string = '{:.%sf} {}' % (num_decimals)
        return format_string.format(quotient, unit)
    elif num == 0:
        return '0 bytes'
    elif num == 1:
        return '1 byte'


def get_size(start_path):
    """
    Get size of the file or directory specified by start_path in bytes.

    If ``start_path`` points to a file - get it's size, if it points to a
    directory - calculate total size of all the files within it
    (including subdirectories).
    """
    # http://stackoverflow.com/a/1392549/176490

    if os.path.isfile(start_path):
        return os.path.getsize(start_path)

    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for filename in filenames:
            fp = os.path.join(dirpath, filename)
            total_size += os.path.getsize(fp)
    return total_size


def get_latest_version_from_pypi():
    try:
        response = requests.get(
            'https://pypi.python.org/pypi/aldryn-client/json'
        )
        response.raise_for_status()
        newest_version = StrictVersion(response.json()['info']['version'])
        return newest_version, None
    except requests.RequestException as exc:
        return False, exc
    except (KeyError, ValueError):
        return False, None


def get_git_commit():
    script_home = os.path.dirname(__file__)
    git_dir = os.path.join(script_home, '..', '.git')
    if os.path.exists(git_dir):
        try:
            return subprocess.check_output([
                'git', '--git-dir', git_dir,
                'rev-parse', '--short', 'HEAD'
            ]).strip()
        except:
            pass


def get_git_checked_branch():
    try:
        git_branch_output = subprocess.check_output(['git', 'branch'])
    except CalledProcessError:
        git_branch_output = None

    aldryn_branch = [branch for branch in git_branch_output.split('\n') if branch.startswith('* ')]

    if aldryn_branch:
        return aldryn_branch[0][2:]
    else:
        return ALDRYN_DEFUALT_BRANCH_NAME


def get_user_agent():
    revision = get_git_commit()
    if revision:
        client = 'aldryn-client/{}-{}'.format(__version__, revision)
    else:
        client = 'aldryn-client/{}'.format(__version__)

    os = '{}/{}'.format(platform.system(), platform.release())
    python = '{}/{}'.format(
        platform.python_implementation(),
        platform.python_version(),
    )
    return '{} ({}; {})'.format(client, os, python)


def download_file(url, directory=None, filename=None):
    response = requests.get(url, stream=True)

    dump_path = os.path.join(
        directory or create_temp_dir(),
        filename or 'data.tar.gz',
    )

    with open(dump_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return dump_path
