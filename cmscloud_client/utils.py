# -*- coding: utf-8 -*-
from cStringIO import StringIO
import tarfile
from cmscloud_client.serialize import register_yaml_extensions
import os
import re
import yaml

FILENAME_BASIC_RE = re.compile(r'^[a-zA-Z_]+[a-zA-Z0-9._-]*\.[a-zA-Z]{2,4}$')
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

def _print(stuff): print stuff

def validate_boilerplate_config(config, errors=_print):
    valid = True
    for thing in BOILERPLATE_REQUIRED:
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

def filter_template_files(tarinfo):
    if not tarinfo.isfile():
        return tarinfo
    basename = os.path.basename(tarinfo.name)
    ext = os.path.splitext(basename)[1]
    if ext == '.html':
        return tarinfo
    else:
        return None

def bundle(config, data, extra_file_paths, **complex_extra):
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
