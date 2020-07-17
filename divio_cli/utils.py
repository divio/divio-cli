import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from distutils.version import StrictVersion
from math import log

from six import PY2
from six.moves.urllib_parse import urljoin

import click
import requests
from tabulate import tabulate

from . import __version__


ALDRYN_DEFAULT_BRANCH_NAME = "develop"


def hr(char="-", width=None, **kwargs):
    if width is None:
        width = click.get_terminal_size()[0]
    click.secho(char * width, **kwargs)


def table(data, headers):
    return tabulate(data, headers)


def get_package_version(path):
    return check_output(["python", "setup.py", "--version"], cwd=path).strip()


@contextmanager
def dev_null():
    with open(os.devnull, "wb") as devnull:
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
    return tempfile.mkdtemp(prefix="tmp_divio_cli_")


def get_bytes_io(*args, **kwargs):
    if PY2:
        from StringIO import StringIO

        cls = StringIO
    else:
        from io import BytesIO

        cls = BytesIO
    return cls(*args, **kwargs)


def get_string_io(*args, **kwargs):
    if PY2:
        from StringIO import StringIO
    else:
        from io import StringIO
    return StringIO(*args, **kwargs)


def tar_add_stringio(tar, string_io, name):
    bytes_io = io.BytesIO(string_io.getvalue().encode())
    return tar_add_bytesio(tar, bytes_io, name)


def tar_add_bytesio(tar, bytes_io, name):
    info = tarfile.TarInfo(name=name)
    bytes_io.seek(0, os.SEEK_END)
    info.size = bytes_io.tell()
    bytes_io.seek(0)
    tar.addfile(tarinfo=info, fileobj=bytes_io)


def get_subprocess_env():
    env = dict(os.environ)
    try:
        # See the following link for details
        # https://github.com/pyinstaller/pyinstaller/blob/master/doc/runtime-information.rst#ld_library_path--libpath-considerations
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    except KeyError:
        pass
    return env


def execute(func, *popenargs, **kwargs):
    if "env" not in kwargs:
        kwargs["env"] = get_subprocess_env()
    catch = kwargs.pop("catch", True)
    if kwargs.pop("silent", False):
        if "stdout" not in kwargs:
            kwargs["stdout"] = open(os.devnull, "w")
            if not is_windows():
                # close file descriptor devnull after exit
                # unfortunately, close_fds is not supported on Windows
                # platforms if you redirect stdin/stdout/stderr
                # => http://svn.python.org/projects/python/
                #    branches/py3k/Lib/subprocess.py
                kwargs["close_fds"] = True
        if "stderr" not in kwargs:
            kwargs["stderr"] = subprocess.STDOUT
    try:
        return func(*popenargs, **kwargs)
    except subprocess.CalledProcessError as exc:
        if not catch:
            raise
        output = (
            "There was an error trying to run a command. This is most likely",
            "not an issue with divio-cli, but the called program itself.",
            "Try checking the output of the command above.",
            "The command was:",
            "  {command}".format(command=" ".join(exc.cmd)),
        )
        hr(fg="red")
        click.secho(os.linesep.join(output), fg="red")
        sys.exit(1)


def check_call(*popenargs, **kwargs):
    return execute(subprocess.check_call, *popenargs, **kwargs)


def check_output(*popenargs, **kwargs):
    return execute(subprocess.check_output, *popenargs, **kwargs).decode()


def open_project_cloud_site(client, project_id, stage):
    project_data = client.get_project(project_id)
    try:
        url = project_data["{}_status".format(stage)]["site_url"]
    except KeyError:
        click.secho(
            "Environment with the name '{}' does not exist.".format(stage), fg="red"
        )
        sys.exit(1)
    if url:
        click.launch(url)
    else:
        click.secho("No {} environment deployed yet.".format(stage), fg="yellow")


def get_cp_url(client, project_id, section="dashboard"):
    project_data = client.get_project(project_id)
    url = project_data["dashboard_url"]

    if section != "dashboard":
        url = urljoin(url, section)

    return url


def is_windows():
    return sys.platform == "win32"


def is_linux():
    return sys.platform.startswith("linux")


unit_list = list(zip(["bytes", "kB", "MB", "GB", "TB", "PB"], [0, 0, 1, 2, 2, 2]))


def pretty_size(num):
    """Human friendly file size"""
    # http://stackoverflow.com/a/10171475
    if num > 1:
        exponent = min(int(log(num, 1024)), len(unit_list) - 1)
        quotient = float(num) / 1024 ** exponent
        unit, num_decimals = unit_list[exponent]
        format_string = "{:.%sf} {}" % num_decimals
        return format_string.format(quotient, unit)
    elif num == 0:
        return "0 bytes"
    elif num == 1:
        return "1 byte"


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
        response = requests.get("https://pypi.python.org/pypi/divio-cli/json")
        response.raise_for_status()
        newest_version = StrictVersion(response.json()["info"]["version"])
        return newest_version, None
    except requests.RequestException as exc:
        return False, exc
    except (KeyError, ValueError):
        return False, None


def get_git_commit():
    script_home = os.path.dirname(__file__)
    git_dir = os.path.join(script_home, "..", ".git")
    if os.path.exists(git_dir):
        try:
            return subprocess.check_output(
                ["git", "--git-dir", git_dir, "rev-parse", "--short", "HEAD"],
                env=get_subprocess_env(),
            ).strip().decode("utf-8")
        except:
            pass


def get_git_checked_branch():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], env=get_subprocess_env()
        ).strip().decode("utf-8")
    except subprocess.CalledProcessError:
        return ALDRYN_DEFAULT_BRANCH_NAME


def get_user_agent():
    revision = get_git_commit()
    if revision:
        client = "divio-cli/{}-{}".format(__version__, revision)
    else:
        client = "divio-cli/{}".format(__version__)

    os_identifier = "{}/{}".format(platform.system(), platform.release())
    python = "{}/{}".format(platform.python_implementation(), platform.python_version())
    return "{} ({}; {})".format(client, os_identifier, python)


def download_file(url, directory=None, filename=None):
    response = requests.get(url, stream=True)

    dump_path = os.path.join(directory or create_temp_dir(), filename or "data.tar.gz")

    with open(dump_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return dump_path


def print_package_renamed_warning():
    message = (
        "aldryn-client has been renamed to divio-cli. Please call it using "
        "`divio` from now on, the shortcut `aldryn` is deprecated and will be "
        "removed in a later version."
    )

    hr(char="=", fg="red")
    click.secho(message, fg="red")
    hr(char="=", fg="red")
    click.echo("")


def json_dumps_unicode(d, **kwargs):
    return json.dumps(d, ensure_ascii=False, **kwargs).encode("utf-8")


class Map(dict):
    """
    A dictionary which also allows accessing values by dot notation.
    Example:
    m = Map({'first_name': 'Eduardo'}, last_name='Pool', age=24, sports=['Soccer'])
    """

    def __init__(self, *args, **kwargs):
        super(Map, self).__init__(*args, **kwargs)
        for arg in args:
            if isinstance(arg, dict):
                for k, v in arg.iteritems():
                    self[k] = v

        if kwargs:
            for k, v in kwargs.iteritems():
                self[k] = v

    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    def __setitem__(self, key, value):
        super(Map, self).__setitem__(key, value)
        self.__dict__.update({key: value})

    def __delattr__(self, item):
        self.__delitem__(item)

    def __delitem__(self, key):
        super(Map, self).__delitem__(key)
        del self.__dict__[key]


def split(delimiters, string, maxsplit=0):
    import re

    regexPattern = "|".join(map(re.escape, delimiters))
    return re.split(regexPattern, string, maxsplit)


def get_local_git_remotes():
    a = check_output(("git", "remote", "-v"))

    ret = []
    for line in a.splitlines():
        name, url, method = split(["\t", " "], line)
        ret.append(url)
    return ret
