# -*- coding: utf-8 -*-
from cStringIO import StringIO
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import yaml

from .serialize import register_yaml_extensions, Trackable, File

FILENAME_BASIC_RE = re.compile(r'^[a-zA-Z0-9_]+[a-zA-Z0-9._-]*(@2x)?\.[a-zA-Z]{2,4}$')
ALLOWED_EXTENSIONS = [
    '.css',
    '.gif',
    '.htc',
    '.htm',
    '.html',
    '.ico',
    '.jpeg',
    '.jpg',
    '.js',
    '.json',
    '.less',
    '.map',
    '.png',
    '.rb',
    '.sass',
    '.scss',
    '.svg',
    '.webm',
    # font formats
    '.eot',
    '.ttf',
    '.woff',
    # text formats
    '.txt',
    '.md',
    '.rst',
    # document formats
    '.pdf',
    '.ps',
    '.djv',
    '.djvu',
    '.doc',
    '.docx',
    '.ppt',
    '.pptx',
    '.xls',
    '.xlsx',
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
    ]),
    'templates',
]

BOILERPLATE_REQUIRED_FILEPATHS = [
    os.path.join('templates', 'base.html'),
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
    ]),
    'installed-apps',
]

VALID_LICENSE_FILENAMES = [
    'LICENSE.txt',
    'LICENSE',
    'license.txt',
    'license',
]


class ValidationError(Exception):
    pass


def _validate(config, required, path):
    license_exists = False
    for valid_license_filename in VALID_LICENSE_FILENAMES:
        license_exists |= os.path.exists(
            os.path.join(path, valid_license_filename))
    if not license_exists:
        return (False, "Required LICENSE.txt file not found")
    valid = (True, "Configuration file is valid")
    for thing in required:
        if isinstance(thing, tuple):
            key, values = thing
        else:
            key, values = thing, []

        if key not in config:
            valid = (False, "Required key %r not found in config" % key)

        for subkey in values:
            if subkey not in config[key]:
                valid = (False, "Required sub key %r in %r not found in config" % (subkey, key))
    return valid


def validate_app_config(config, path):
    return _validate(config, APP_REQUIRED, path)


def validate_boilerplate_config(config, path):
    for required_filepath in BOILERPLATE_REQUIRED_FILEPATHS:
        dirpath = os.path.join(path, required_filepath)
        if not os.path.exists(dirpath):
            msg = 'Required file "%s" not found' % required_filepath
            return (False, msg)
    (valid, msg) = _validate(config, BOILERPLATE_REQUIRED, path)
    if not valid:
        return (False, msg)
    # check templates
    data = config.get('templates', [])
    template_valid = True
    if not isinstance(data, list):
        template_valid = False
    else:
        for template in data:
            if not isinstance(template, list):
                template_valid = False
            elif len(template) != 2:
                template_valid = False
    if not template_valid:
        msg = "Templates must be a list of lists of two items"
        return (False, msg)

    # check protected
    protected = config.get('protected', [])
    valid = True
    if not isinstance(protected, list):
        valid = False
        msg = "Protected files must be a list"
    else:
        errors = []
        for filename in protected:
            filepath = os.path.join(path, filename)
            if not os.path.exists(filepath):
                valid = False
                errors.append("Protected file %r not found" % filename)
        if errors:
            msg = os.linesep.join(errors)
    return (valid, msg)


def tar_add_stringio(tar, string_io, name):
    info = tarfile.TarInfo(name=name)
    string_io.seek(0, os.SEEK_END)
    info.size = string_io.tell()
    string_io.seek(0)
    tar.addfile(tarinfo=info, fileobj=string_io)


def is_valid_file_name(name, logger=None):
    if not FILENAME_BASIC_RE.match(name):
        if logger:
            logger("File name %r is not valid, ignoring." % name)
        return False
    ext = os.path.splitext(name)[-1]
    if ext not in ALLOWED_EXTENSIONS:
        if logger:
            logger("File extension %r is not allowed, ignoring." % ext)
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


def _get_license_filename(path):
    for valid_license_filename in VALID_LICENSE_FILENAMES:
        filepath = os.path.join(path, valid_license_filename)
        if os.path.exists(filepath):
            return filepath


def load_license(path):
    filepath = _get_license_filename(path)
    if filepath:
        with open(filepath, 'r') as f:
            license = f.read()
            return license


def bundle_boilerplate(config, data, path, extra_file_paths, **complex_extra):
    register_yaml_extensions()
    fileobj = StringIO()
    tar = tarfile.open(mode='w:gz', fileobj=fileobj)
    config_fileobj = StringIO()
    json.dump(config, config_fileobj)
    tar_add_stringio(tar, config_fileobj, 'boilerplate.json')
    data_fileobj = StringIO()
    yaml.safe_dump(data, data_fileobj)
    tar_add_stringio(tar, data_fileobj, 'data.yaml')
    license_filepath = _get_license_filename(path)
    if license_filepath:
        tar.add(license_filepath, 'LICENSE.txt')
    for extra_path in extra_file_paths:
        tar.add(extra_path)
    for key, value in complex_extra.items():
        dirpath = os.path.join(path, key)
        if os.path.exists(dirpath):
            tar.add(key, filter=value)
    tar.close()
    fileobj.seek(0)
    return fileobj


def bundle_package(workspace, tar, path):
    devnull = open(os.devnull, 'w')
    try:
        subprocess.check_call(['python', 'setup.py', 'sdist', '-d', workspace],
                              cwd=path, stdout=devnull, stderr=devnull)
    finally:
        devnull.close()
    egg_file = os.path.join(workspace, os.listdir(workspace)[0])
    tar.add(egg_file, arcname='package.tar.gz')


def bundle_app(config, script, path):
    register_yaml_extensions()
    fileobj = StringIO()
    tar = tarfile.open(mode='w:gz', fileobj=fileobj)
    config_fileobj = StringIO()
    json.dump(config, config_fileobj)
    tar_add_stringio(tar, config_fileobj, 'addon.json')
    script_fileobj = StringIO(script)
    license_filepath = _get_license_filename(path)
    if license_filepath:
        tar.add(license_filepath, 'LICENSE.txt')
    if os.path.exists('aldryn_config.py'):
        tar_add_stringio(tar, script_fileobj, 'aldryn_config.py')
        # add actual package
    distdir = tempfile.mkdtemp(prefix='aldryn-client')
    try:
        bundle_package(distdir, tar, path)
    finally:
        shutil.rmtree(distdir)
    tar.close()
    fileobj.seek(0)
    return fileobj


def hashfile(fd, blocksize=65536):
    hasher = hashlib.sha256()
    buf = fd.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = fd.read(blocksize)
    return hasher.digest()


def uniform_filepath(filepath):
    filepath = os.path.abspath(filepath)
    filepath = os.path.realpath(filepath)
    filepath = filepath.rstrip(os.sep)
    return filepath


def is_hidden(path):
    filename = os.path.basename(path)
    return filename.startswith('.')


def is_inside_dir(path, parent_dir):
    path = os.path.join(parent_dir, path)
    path = uniform_filepath(path)
    return path.startswith(parent_dir)


def filter_bad_paths(members, parent_dir):
    parent_dir = uniform_filepath(parent_dir)
    for finfo in members:
        if (not finfo.issym() and not finfo.islnk() and
                is_inside_dir(finfo.path, parent_dir)):
            yield finfo


def resource_path(relative_path):
    """
    Get absolute path of the resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = os.sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


def cli_confirm(question, message=None, default=None):
    if message:
        print message

    if default is None:
        default_answer_str = '[y/n]'
    else:
        default = bool(default)
        if default is True:
            default_answer_str = '[Y/n]'
        elif default is False:
            default_answer_str = '[y/N]'

    question = '%s %s' % (question.rstrip(), default_answer_str)
    while True:
        answer = raw_input(question)
        if answer.lower() == 'y':
            return True
        elif answer.lower() == 'n':
            return False
        elif default is not None and answer == '':
            return default
        else:
            print "Invalid answer, please type either y or n"


def load_boilerplate_config(path):
    from .client import Client
    boilerplate_filename_json = os.path.join(path, Client.BOILERPLATE_FILENAME_JSON)
    boilerplate_filename_yaml = os.path.join(path, Client.BOILERPLATE_FILENAME_YAML)
    boilerplate_filename = None
    load_json_config = False
    if os.path.exists(boilerplate_filename_yaml):
        boilerplate_filename = boilerplate_filename_yaml
    if os.path.exists(boilerplate_filename_json):
        if boilerplate_filename is None:
            boilerplate_filename = boilerplate_filename_json
            load_json_config = True
        else:
            msg = "Please provide only one config file ('%s' or '%s')" % (
                Client.BOILERPLATE_FILENAME_JSON,
                Client.BOILERPLATE_FILENAME_YAML)
            return (False, msg)
    if boilerplate_filename is None:
        msg = "Neither file '%s' nor '%s' were found." % (
            Client.BOILERPLATE_FILENAME_JSON, Client.BOILERPLATE_FILENAME_YAML)
        return (False, msg)
    extra_file_paths = []
    with open(boilerplate_filename) as fobj:
        try:
            if load_json_config:
                config = json.load(fobj)
            else:
                with Trackable.tracker as extra_objects:
                    config = yaml.safe_load(fobj)
                    extra_file_paths.extend([f.path for f in extra_objects[File]])
        except (yaml.YAMLError, ValueError) as e:
            return (False, repr(e))
        return (True, (config, extra_file_paths))


def load_app_config(path):
    from .client import Client
    app_filename_json = os.path.join(path, Client.APP_FILENAME_JSON)
    app_filename_yaml = os.path.join(path, Client.APP_FILENAME_YAML)
    addon_filename_json = os.path.join(path, Client.ADDON_FILENAME_JSON)
    addon_filename_yaml = os.path.join(path, Client.ADDON_FILENAME_YAML)
    app_filenames = []
    load_json_config = False
    if os.path.exists(app_filename_yaml):
        app_filenames.append(app_filename_yaml)
    if os.path.exists(addon_filename_yaml):
        app_filenames.append(addon_filename_yaml)
    if os.path.exists(app_filename_json):
        app_filenames.append(app_filename_json)
        load_json_config = True
    if os.path.exists(addon_filename_json):
        app_filenames.append(addon_filename_json)
        load_json_config = True
    if len(app_filenames) == 0:
        msg = "File '%s' not found." % Client.ADDON_FILENAME_JSON
        return (False, msg)
    elif len(app_filenames) == 1:
        app_filename = app_filenames[0]
    else:
        msg = "Please provide only one config file (%s)" % (
            ' or '.join(map(os.path.basename, app_filenames)),)
        return (False, msg)
    with open(app_filename) as fobj:
        try:
            if load_json_config:
                config = json.load(fobj)
            else:
                config = yaml.safe_load(fobj)
        except (yaml.YAMLError, ValueError) as e:
            return (False, repr(e))
    return (True, config)
