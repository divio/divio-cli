# -*- coding: utf-8 -*-
import subprocess
import tarfile
import tempfile
import os
import sys
from contextlib import contextmanager

import click
from tabulate import tabulate


def hr(char='─', width=None, **kwargs):
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
        exit(-1)


def check_call(*popenargs, **kwargs):
    return execute(subprocess.check_call, *popenargs, **kwargs)


def check_output(*popenargs, **kwargs):
    return execute(subprocess.check_output, *popenargs, **kwargs)


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
