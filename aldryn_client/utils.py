# -*- coding: utf-8 -*-
from cStringIO import StringIO
import hashlib
import imp
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import yaml
import platform


FILENAME_BASIC_RE = re.compile(r'^[a-zA-Z0-9_@]+[a-zA-Z0-9._@-]*\.[a-zA-Z0-9]{1,23}$')
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
    '.woff2',
    '.otf',
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
    'package-name',
    'identifier',
    'version',
    'templates',
]

BOILERPLATE_REQUIRED_MSG = {
    'package-name': "The specs for boilerplate.json have recently changed. 'package-name' is a new mandatory field.\n"
                    "If you previously already uploaded this Boilerplate without a 'package-name', you can set a "
                    "package-name at https://control.aldryn.com/account/my-boilerplates/.\n",
}

BOILERPLATE_DEPRECATED_FIELDS = [
    'name',
    'description',
    'url',
    'public',
    'license',
    'author',
]

BOILERPLATE_REQUIRED_FILEPATHS = [
    os.path.join('templates', 'base.html'),
]

APP_REQUIRED = [
    'package-name',
    'installed-apps',
]

APP_DEPRECATED_FIELDS = [
    'name',
    'description',
    'url',
    'public',
    'license',
    'author',
    'version',
]

VALID_LICENSE_FILENAMES = [
    'LICENSE.txt',
    'LICENSE',
    'license.txt',
    'license',
]


class ValidationError(Exception):
    pass


def _validate(config, required, path, required_msg=None):
    required_msg = {} if required_msg is None else required_msg
    license_exists = False
    for valid_license_filename in VALID_LICENSE_FILENAMES:
        license_exists |= os.path.exists(
            os.path.join(path, valid_license_filename))
    if not license_exists:
        return (False, "Required LICENSE.txt file not found")
    valid = True
    valid_msg = []
    for thing in required:
        if isinstance(thing, tuple):
            key, values = thing
        else:
            key, values = thing, []

        if key not in config:
            valid = False

            valid_msg.append(required_msg.get(
                key,
                "Required key %r not found in config" % key
            ))

        for subkey in values:
            if subkey not in config[key]:
                valid = (False, "Required sub key %r in %r not found in config" % (subkey, key))
    if valid and not valid_msg:
        valid_msg = ["Configuration file is valid"]
    return valid, '\n'.join(valid_msg)


def _check_deprecated_fields(config, fields):
    return [
        field for field in fields
        if field in config
    ]


def validate_app_config(config, path):
    aldryn_config_path = os.path.abspath(os.path.join(path, 'aldryn_config.py'))
    if os.path.exists(aldryn_config_path):
        tempdir = tempfile.mkdtemp(prefix='tmp_aldryn_client_')
        try:
            shutil.copy(aldryn_config_path, tempdir)
            filepath = os.path.join(tempdir, 'aldryn_config.py')
            try:
                orig_err = sys.stderr
                sys.stderr = StringIO()
                # suppressing "RuntimeWarning: Parent module 'aldryn_config' not found while handling absolute import"
                module = imp.load_source('aldryn_config.config_%s' % int(time.time()), filepath)
                sys.stderr = orig_err
                # checking basic functionality of the Form
                form = module.Form({})
                form.is_valid()
            except Exception:
                import traceback
                error_msg = traceback.format_exc()
                return (False, "Exception in aldryn_config.py:\n\n%s" % error_msg)
        finally:
            shutil.rmtree(tempdir)
    valid, msg = _validate(config, APP_REQUIRED, path)
    # warn about deprecated fields
    depricated_fields = _check_deprecated_fields(config, APP_DEPRECATED_FIELDS)
    if depricated_fields:
        msg += (
            "\n\nDeprecation warning! "
            "These fields are ignored. It's recommended to remove them from addon.json and use the web interface ({0}) to edit them instead.\n"
        ).format('https://control.aldryn.com/account/my-addons/')
        msg += '\n'.join(['  - {0}'.format(field) for field in depricated_fields])
    return valid, msg


def validate_boilerplate_config(config, path):
    for required_filepath in BOILERPLATE_REQUIRED_FILEPATHS:
        dirpath = os.path.join(path, required_filepath)
        if not os.path.exists(dirpath):
            msg = 'Required file "%s" not found' % required_filepath
            return (False, msg)
    (valid, msg) = _validate(config, BOILERPLATE_REQUIRED, path, BOILERPLATE_REQUIRED_MSG)
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
            if filepath.endswith('*'):
                continue
            if not os.path.exists(filepath):
                valid = False
                errors.append("Protected file %r not found" % filename)
        if errors:
            msg = os.linesep.join(errors)
    # warn about deprecated fields
    depricated_fields = _check_deprecated_fields(config, BOILERPLATE_DEPRECATED_FIELDS)
    if depricated_fields:
        msg += (
            "\n\nDeprecation warning! "
            "These fields are ignored. It's recommended to remove them from boilerplate.json and use the web interface ({0}) to edit them instead.\n"
        ).format('https://control.aldryn.com/account/my-boilerplates/')
        msg += '\n'.join(['  - {0}'.format(field) for field in depricated_fields])
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


def bundle_boilerplate(config, path, **complex_extra):
    fileobj = StringIO()
    tar = tarfile.open(mode='w:gz', fileobj=fileobj)
    config_fileobj = StringIO()
    json.dump(config, config_fileobj)
    tar_add_stringio(tar, config_fileobj, 'boilerplate.json')
    data_fileobj = StringIO()
    tar_add_stringio(tar, data_fileobj, 'data.yaml')
    license_filepath = _get_license_filename(path)
    if license_filepath:
        tar.add(license_filepath, 'LICENSE.txt')
    for key, value in complex_extra.items():
        dirpath = os.path.join(path, key)
        if os.path.exists(dirpath):
            tar.add(key, filter=value)
    tar.close()
    fileobj.seek(0)
    return fileobj


def get_package_version(path):
    devnull = open(os.devnull, 'w')
    try:
        version = subprocess.check_output(
            ['python', 'setup.py', '--version'], cwd=path, stderr=devnull)
    finally:
        devnull.close()
    return version.strip()


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
    distdir = tempfile.mkdtemp(prefix='tmp_aldryn_client_')
    try:
        bundle_package(distdir, tar, path)
    finally:
        shutil.rmtree(distdir)
    version = get_package_version(path)
    version_fobj = StringIO(version)
    info = tarfile.TarInfo(name='VERSION')
    info.size = len(version_fobj.getvalue())
    tar.addfile(info, fileobj=version_fobj)
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


def get_icon_path():
    system = platform.system()
    if system == 'Darwin':
        icon = 'resources/appIcon.icns'
    elif system == 'Windows':
        icon = 'resources/appIcon.ico'
    else:
        icon = 'resources/appIcon.png'
    return resource_path(icon)


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
    boilerplate_filename = os.path.join(path, Client.BOILERPLATE_FILENAME_JSON)
    if not os.path.exists(boilerplate_filename):
        msg = "Please provide a %s config file" % Client.BOILERPLATE_FILENAME_JSON
        return (False, msg)
    with open(boilerplate_filename) as fobj:
        try:
            config = json.load(fobj)
        except ValueError as e:
            return (False, repr(e))
        return (True, config,)


def load_app_config(path):
    from .client import Client
    app_filename_json = os.path.join(path, Client.APP_FILENAME_JSON)
    addon_filename_json = os.path.join(path, Client.ADDON_FILENAME_JSON)
    app_filenames = []
    if os.path.exists(app_filename_json):
        app_filenames.append(app_filename_json)
    if os.path.exists(addon_filename_json):
        app_filenames.append(addon_filename_json)
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
            config = json.load(fobj)
        except (ValueError) as e:
            return (False, repr(e))
    return (True, config)
