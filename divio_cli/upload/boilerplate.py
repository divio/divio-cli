import glob
import os
import tarfile

import click

from .. import settings
from ..utils import get_bytes_io
from ..validators.boilerplate import validate_boilerplate
from ..validators.common import load_config
from .common import add_meta_files


BOILERPLATE_EXCLUDE_DEFAULTS = ["boilerplate.json", ".git"]


def normalize_path(path):
    return os.path.normpath(path)


def get_boilerplate_files(boilerplate_path):
    config = load_config(settings.BOILERPLATE_CONFIG_FILENAME, boilerplate_path)
    excluded_patterns = config.get("excluded", []) + BOILERPLATE_EXCLUDE_DEFAULTS
    # glob excludes
    excluded = []
    for exclude in excluded_patterns:
        excluded += glob.glob(normalize_path(exclude).rstrip("/"))

    excluded = set(excluded)
    matches = []

    for path, subdirs, files in os.walk(boilerplate_path, topdown=True):
        subdirs[:] = [
            sub
            for sub in subdirs
            if normalize_path(os.path.join(path, sub)) not in excluded
        ]

        if normalize_path(path) not in excluded:  # check root level excludes
            for fname in files:
                fpath = os.path.join(path, fname)
                if normalize_path(fpath) not in excluded:
                    matches.append(fpath)

    return excluded, matches


def upload_boilerplate(client, path=None, noinput=False):
    path = path or "."
    errors = validate_boilerplate(path)

    if errors:
        message = "The following errors happened during validation:"
        message = "{}\n - {}".format(message, "\n - ".join(errors))
        raise click.ClickException(message)

    excludes, files = get_boilerplate_files(path)

    if not noinput:
        click.secho(
            "The following files will be included in your "
            "boilerplate and uploaded to the Divio Cloud:".format(len(files)),
            fg="yellow",
        )
        click.echo(os.linesep.join(files))
        click.confirm(
            "Are you sure you want to continue and upload "
            "the preceding (#{}) files to the Divio Cloud?".format(len(files)),
            default=True,
            show_default=True,
            abort=True,
        )

    archive_obj = create_boilerplate_archive(path, files)
    return client.upload_boilerplate(archive_obj)


def create_boilerplate_archive(path, files):
    fobj = get_bytes_io()

    with tarfile.open(mode="w:gz", fileobj=fobj) as tar:
        add_meta_files(tar, path, settings.BOILERPLATE_CONFIG_FILENAME)
        for f in files:
            tar.add(f)

    fobj.seek(0)
    return fobj
