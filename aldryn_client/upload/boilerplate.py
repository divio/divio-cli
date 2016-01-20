import os
import tarfile

from six import StringIO

from .. import settings
from ..utils import tar_add_stringio
from ..validators.common import load_config, is_valid_file_name
from ..validators.boilerplate import validate_boilerplate
from .common import add_meta_files


def add_boilerplate_files(path, tar, **complex_extra):
    data_fileobj = StringIO()
    tar_add_stringio(tar, data_fileobj, 'data.yaml')
    for key, value in complex_extra.items():
        dirpath = os.path.join(path, key)
        if os.path.exists(dirpath):
            tar.add(key, filter=value)

    config = load_config(settings.BOILERPLATE_CONFIG_FILENAME, path)
    special_files = [
        f for f in config['protected']
        if not any([f.startswith(key) for key in complex_extra.keys()])
    ]
    for special_file in special_files:
        tar.add(special_file)


def filter_template_files(tarinfo):
    if not tarinfo.isfile():
        return tarinfo
    basename = os.path.basename(tarinfo.name)
    ext = os.path.splitext(basename)[1]
    if ext == '.html':
        return tarinfo
    else:
        return None


def filter_static_files(tarinfo):
    if not tarinfo.isfile():
        return tarinfo
    basename = os.path.basename(tarinfo.name)
    if is_valid_file_name(basename):
        return tarinfo
    else:
        return None


def filter_sass_files(tarinfo):
    basename = os.path.basename(tarinfo.name)
    if tarinfo.isfile():
        if is_valid_file_name(basename):
            return tarinfo
        else:
            return None
    elif basename.startswith('.'):
        return None
    else:
        return tarinfo


def create_boilerplate_archive(path):
    data = StringIO()

    with tarfile.open(mode='w:gz', fileobj=data) as tar:
        add_meta_files(tar, path, settings.BOILERPLATE_CONFIG_FILENAME)
        add_boilerplate_files(
            path, tar,
            templates=filter_template_files,
            static=filter_static_files,
            private=filter_sass_files,
        )

    data.seek(0)
    return data


def upload_boilerplate(client, path=None):
    path = path or '.'
    validate_boilerplate(path)
    archive_obj = create_boilerplate_archive(path)
    return client.upload_boilerplate(archive_obj)
