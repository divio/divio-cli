# -*- coding: utf-8 -*-
from cStringIO import StringIO
import shutil
import subprocess
import tarfile
import tempfile
from cmscloud_client.serialize import register_yaml_extensions
import os
import re
import yaml

FILENAME_BASIC_RE = re.compile(r'^[a-zA-Z0-9_]+[a-zA-Z0-9._-]*\.[a-zA-Z]{2,4}$')
ALLOWED_EXTENSIONS = [
    '.js',
    '.css',
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.htc',
    '.scss',
    '.sass',
    '.rb',
    '.less',
    '.ico',
    '.html',
    '.htm',
]

BOILERPLATE_REQUIRED = [
    'name',
    ('author', [
        'name',
    ]),
    'version',
    'description',
    ('license', [
        'name',
        'text',
    ]),
    'templates',
]

APP_REQUIRED = [
    'name',
    ('author', [
        'name',
    ]),
    'version',
    'package-name',
    'description',
    ('license', [
        'name',
        'text'
    ]),
    'installed-apps',
]


def _print(stuff): print stuff


def _validate(config, required, errors):
    valid = True
    for thing in required:
        if isinstance(thing, tuple):
            key, values = thing
        else:
            key, values = thing, []

        if key not in config:
            errors("Required key %r not found in config" % key)
            valid = False

        for subkey in values:
            if subkey not in config[key]:
                errors("Required sub key %r in %r not found in config" % (subkey, key))
                valid = False
    return valid


def validate_app_config(config, errors=_print):
    return _validate(config, APP_REQUIRED, errors)


def validate_boilerplate_config(config, errors=_print):
    valid = _validate(config, BOILERPLATE_REQUIRED, errors)
    # check templates
    data = config.get('templates', [])
    if not isinstance(data, list):
        errors("Templates must be a list of lists of two items")
        valid = False
    else:
        for template in data:
            if not isinstance(template, list):
                errors("Templates must be a list of lists of two items")
                valid = False
            elif len(template) != 2:
                errors("Templates must be a list of lists of two items")
                valid = False
    # check protected
    protected = config.get('protected', [])
    if not isinstance(protected, list):
        valid = False
        errors( "Protected files must be a list")
    else:
        for filename in protected:
            if not os.path.exists(filename):
                valid = False
                errors("Protected file %r not found" % filename)
    return valid


def tar_add_stringio(tar, string_io, name):
    info = tarfile.TarInfo(name=name)
    string_io.seek(0, os.SEEK_END)
    info.size = string_io.tell()
    string_io.seek(0)
    tar.addfile(tarinfo=info, fileobj=string_io)


def is_valid_file_name(name, printer=None):
    always_print = printer.always if printer else lambda x: None
    if not FILENAME_BASIC_RE.match(name):
        always_print("File name %r is not a valid file name, ignoring..." % name)
        return False
    ext = os.path.splitext(name)[-1]
    if ext not in ALLOWED_EXTENSIONS:
        always_print("File extension %r is not allowed, ignoring" % ext)
        return False
    return True


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


def filter_template_files(tarinfo):
    if not tarinfo.isfile():
        return tarinfo
    basename = os.path.basename(tarinfo.name)
    ext = os.path.splitext(basename)[1]
    if ext == '.html':
        return tarinfo
    else:
        return None


def bundle_boilerplate(config, data, extra_file_paths, **complex_extra):
    register_yaml_extensions()
    fileobj = StringIO()
    tar = tarfile.open(mode='w:gz', fileobj=fileobj)
    config_fileobj = StringIO()
    yaml.dump(config, config_fileobj)
    tar_add_stringio(tar, config_fileobj, 'boilerplate.yaml')
    data_fileobj = StringIO()
    yaml.dump(data, data_fileobj)
    tar_add_stringio(tar, data_fileobj, 'data.yaml')
    for path in extra_file_paths:
        tar.add(path)
    for key, value in complex_extra.items():
        tar.add(key, filter=value)
    tar.close()
    fileobj.seek(0)
    return fileobj


def bundle_package(workspace, tar):
    devnull = open(os.devnull, 'w')
    try:
        subprocess.check_call(['python', 'setup.py', 'sdist', '-d', workspace], stdout=devnull, stderr=devnull)
    finally:
        devnull.close()
    egg_file = os.path.join(workspace, os.listdir(workspace)[0])
    tar.add(egg_file, arcname='package.tar.gz')


def bundle_app(config, script):
    register_yaml_extensions()
    fileobj = StringIO()
    tar = tarfile.open(mode='w:gz', fileobj=fileobj)
    config_fileobj = StringIO()
    yaml.dump(config, config_fileobj)
    tar_add_stringio(tar, config_fileobj, 'app.yaml')
    script_fileobj = StringIO(script)
    if os.path.exists('cmscloud_config.py'):
        tar_add_stringio(tar, script_fileobj, 'cmscloud_config.py')
        # add actual package
    distdir = tempfile.mkdtemp(prefix='cmscloud-client')
    try:
        bundle_package(distdir, tar)
    finally:
        shutil.rmtree(distdir)
    tar.close()
    fileobj.seek(0)
    return fileobj
