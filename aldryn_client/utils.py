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
    with dev_null() as devnull:
        version = execute(
            ['python', 'setup.py', '--version'],
            cwd=path, stderr=devnull, silent=True,
        )
        return version.strip()


@contextmanager
def dev_null():
    with open(os.devnull, 'wb') as devnull:
        yield devnull


@contextmanager
def silence_stderr():
    try:
        with dev_null() as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = sys.__stderr__


@contextmanager
def silence_stdout():
    try:
        with dev_null() as devnull:
            sys.stdout = devnull
            yield
    finally:
        sys.stderr = sys.__stdout__


def create_temp_dir():
    return tempfile.mkdtemp(prefix='tmp_aldryn_client_')


def tar_add_stringio(tar, string_io, name):
    info = tarfile.TarInfo(name=name)
    string_io.seek(0, os.SEEK_END)
    info.size = string_io.tell()
    string_io.seek(0)
    tar.addfile(tarinfo=info, fileobj=string_io)


def execute(*popenargs, **kwargs):
    """
    Modified version of subprocess.check_output that prints
    stdout as soon as it's available instead of holding it back
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    silence_output = kwargs.pop('silent', False)
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    if not silence_output:
        lines_iterator = iter(process.stdout.readline, b'')
        for line in lines_iterator:
            click.echo(line, nl=False)

    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get('args')
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd, output=output)
    return output
