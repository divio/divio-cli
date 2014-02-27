# -*- coding: utf-8 -*-
import datetime
import getpass
import json
import netrc
import os
import time
import shutil
import stat
import urlparse

import git
import requests
import yaml

from .serialize import register_yaml_extensions, Trackable, File
from .git_sync import GitSyncHandler
from .sync_helpers import (
    extra_git_kwargs, git_update_gitignore, git_pull_develop_bundle)
from .utils import (
    validate_boilerplate_config, bundle_boilerplate, filter_template_files,
    filter_static_files, validate_app_config, bundle_app, filter_sass_files,
    resource_path, cli_confirm, load_app_config, load_boilerplate_config)


CACERT_PEM_PATH = resource_path('cacert.pem')


class WritableNetRC(netrc.netrc):
    def __init__(self, *args, **kwargs):
        netrc_path = self.get_netrc_path()
        if not os.path.exists(netrc_path):
            open(netrc_path, 'a').close()
            os.chmod(netrc_path, 0600)
        # XXX netrc uses os.environ['HOME'] which isn't defined on Windows
        os.environ['HOME'] = os.path.expanduser('~')
        netrc.netrc.__init__(self, *args, **kwargs)

    def get_netrc_path(self):
        home = os.path.expanduser('~')
        return os.path.join(home, '.netrc')

    def add(self, host, login, account, password):
        self.hosts[host] = (login, account, password)

    def remove(self, host):
        if host in self.hosts:
            del self.hosts[host]

    def write(self, path=None):
        if path is None:
            path = self.get_netrc_path()
        with open(path, 'w') as fobj:
            for machine, data in self.hosts.items():
                login, account, password = data
                fobj.write('machine %s\n' % machine)
                if login:
                    fobj.write('\tlogin %s\n' % login)
                if account:
                    fobj.write('\taccount %s\n' % account)
                if password:
                    fobj.write('\tpassword %s\n' % password)


class SingleHostSession(requests.Session):
    def __init__(self, host, **kwargs):
        super(SingleHostSession, self).__init__()
        self.host = host.rstrip('/')
        for key, value in kwargs.items():
            setattr(self, key, value)

    def request(self, method, url, *args, **kwargs):
        url = self.host + url
        # Use local copy of 'cacert.pem' for easier packaging
        kwargs['verify'] = CACERT_PEM_PATH
        return super(SingleHostSession, self).request(method, url, *args, **kwargs)


class Client(object):
    APP_FILENAME_JSON = 'app.json'
    APP_FILENAME_YAML = 'app.yaml'
    ADDON_FILENAME_JSON = 'addon.json'
    ADDON_FILENAME_YAML = 'addon.yaml'
    BOILERPLATE_FILENAME_JSON = 'boilerplate.json'
    BOILERPLATE_FILENAME_YAML = 'boilerplate.yaml'
    ALDRYN_CONFIG_FILENAME = 'aldryn_config.py'
    ALDRYN_DOT_FILENAME = '.aldryn'
    ALDRYN_HOST_DEFAULT = 'https://control.aldryn.com'
    ALDRYN_HOST_KEY = 'ALDRYN_HOST'
    ALDRYN_SYNC_LOCK_FILENAME = '.aldryn-sync-lock'
    DATA_FILENAME = 'data.yaml'
    PROTECTED_FILES_FILENAME = '.protected_files'
    SETUP_FILENAME = 'setup.py'

    # messages
    DIRECTORY_ALREADY_SYNCING_MESSAGE = 'Directory already syncing.'
    NETWORK_ERROR_MESSAGE = 'Network error.\nPlease check your connection and try again later.'
    PROTECTED_FILE_CHANGE_MESSAGE = 'You are overriding file "%s".\nThis file is protected by the boilerplate.'
    SYNC_NETWORK_ERROR_MESSAGE = "Couldn't sync changes.\nPlease check your connection and try again later."

    ALL_CONFIG_FILES = [
        APP_FILENAME_JSON, APP_FILENAME_YAML,
        BOILERPLATE_FILENAME_JSON, BOILERPLATE_FILENAME_YAML,
        ALDRYN_CONFIG_FILENAME, SETUP_FILENAME, DATA_FILENAME]

    def __init__(self, host, interactive=True):
        register_yaml_extensions()
        self.host = urlparse.urlparse(host)[1]
        self.interactive = interactive
        self.netrc = WritableNetRC()
        auth_data = self.get_auth_data()
        if auth_data:
            headers = {
                'Authorization': 'Basic %s' % auth_data[2]
            }
        else:
            headers = {}
        self.session = SingleHostSession(
            host, headers=headers, trust_env=False)

        self._sync_handlers_cache = {}

    def get_auth_data(self):
        return self.netrc.hosts.get(self.host)

    def is_logged_in(self):
        auth_data = self.get_auth_data()
        return bool(auth_data)

    def get_login(self):
        if self.is_logged_in():
            auth_data = self.get_auth_data()
            return auth_data[0]

    def logout(self):
        while self.interactive:
            answer = raw_input('Are you sure you want to continue? [yN]')
            if answer.lower() == 'n' or not answer:
                print "Aborted"
                return True
            elif answer.lower() == 'y':
                break
            else:
                print "Invalid answer, please type either y or n"
        self.netrc.remove(self.host)
        self.netrc.write()

    def login(self, email=None, password=None):
        if email is None:
            email = raw_input('E-Mail: ')
        if password is None:
            password = getpass.getpass('Password: ')
        try:
            response = self.session.post(
                '/api/v1/login/', data={'email': email, 'password': password})
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return (False, Client.NETWORK_ERROR_MESSAGE)
        if response.ok:
            token = response.content
            self.session.headers = {
                'Authorization': 'Basic %s' % token
            }
            self.netrc.add(self.host, email, None, token)
            self.netrc.write()
            msg = "Logged in as %s" % email
            return (True, msg)
        elif response.status_code == requests.codes.forbidden:
            if response.content:
                msg = response.content
            else:
                msg = "Could not log in, invalid email or password"
            return (False, msg)
        else:
            msgs = []
            if response.content and response.status_code < 500:
                msgs.append(response.content)
            msgs.append("There was a problem logging in, please try again later.")
            return (False, '\n'.join(msgs))

    def upload_boilerplate(self, path='.'):
        is_loaded, result = load_boilerplate_config(path)
        if is_loaded:
            config, extra_file_paths = result
        else:
            return (False, result)
        data_filename = os.path.join(path, Client.DATA_FILENAME)
        if os.path.exists(data_filename):
            with Trackable.tracker as extra_objects:
                with open(data_filename) as fobj2:
                    data = yaml.safe_load(fobj2)
                extra_file_paths.extend([f.path for f in extra_objects[File]])
        else:
            data = {}
        is_valid, error_msg = validate_boilerplate_config(config, path)
        if not is_valid:
            return (False, error_msg)
        tarball = bundle_boilerplate(config, data, path, extra_file_paths, templates=filter_template_files,
                                     static=filter_static_files, private=filter_sass_files)
        try:
            response = self.session.post('/api/v1/boilerplates/', files={'boilerplate': tarball})
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return (False, Client.NETWORK_ERROR_MESSAGE)
        msg = '\t'.join([str(response.status_code), response.content])
        return (True, msg)

    def validate_boilerplate(self, path='.'):
        is_loaded, result = load_boilerplate_config(path)
        if is_loaded:
            config, extra_file_paths = result
            return validate_boilerplate_config(config, path)
        else:
            return (False, result)

    def upload_app(self, path='.'):
        is_loaded, result = load_app_config(path)
        if is_loaded:
            config = result
        else:
            return (False, result)
        is_valid, msg = validate_app_config(config, path)
        if not is_valid:
            return (False, msg)
        setup_filename = os.path.join(path, Client.SETUP_FILENAME)
        if not os.path.exists(setup_filename):
            msg = "File '%s' not found." % Client.SETUP_FILENAME
            return (False, msg)
        aldryn_config_filename = os.path.join(
            path, Client.ALDRYN_CONFIG_FILENAME)
        msgs = []
        if os.path.exists(aldryn_config_filename):
            with open(aldryn_config_filename) as fobj:
                script = fobj.read()
        else:
            script = ''
            msgs.append("Warning: File '%s' not found." % Client.ALDRYN_CONFIG_FILENAME)
            msgs.append("Your app will not have any configurable settings.")
        tarball = bundle_app(config, script, path)
        try:
            response = self.session.post('/api/v1/apps/', files={'app': tarball})
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return (False, Client.NETWORK_ERROR_MESSAGE)
        msgs.append('\t'.join([str(response.status_code), response.content]))
        return (True, '\n'.join(msgs))

    def validate_app(self, path='.'):
        setup_filename = os.path.join(path, Client.SETUP_FILENAME)
        if not os.path.exists(setup_filename):
            msg = "File '%s' not found." % Client.SETUP_FILENAME
            return (False, msg)
        is_loaded, result = load_app_config(path)
        if is_loaded:
            config = result
            return validate_app_config(config, path)
        else:
            return (False, result)

    def _acquire_sync_lock(self, sync_dir):
        lock_filename = os.path.join(
            sync_dir, Client.ALDRYN_SYNC_LOCK_FILENAME)
        try:
            fd = os.open(lock_filename, os.O_CREAT | os.O_EXCL)
            os.close(fd)
        except OSError:
            return False
        else:
            return True

    def _remove_sync_lock(self, sync_dir):
        lock_filename = os.path.join(
            sync_dir, Client.ALDRYN_SYNC_LOCK_FILENAME)
        if os.path.exists(lock_filename):
            os.remove(lock_filename)

    def sync(self, network_error_callback, sync_error_callback,
             protected_file_change_callback, sitename=None, path='.', force=False,
             sync_indicator_callback=None, stop_sync_callback=None):
        aldryn_dot_filename = os.path.join(path, Client.ALDRYN_DOT_FILENAME)
        if not sitename:
            if os.path.exists(aldryn_dot_filename):
                with open(aldryn_dot_filename, 'r') as fobj:
                    sitename = fobj.read().strip()
            if not sitename:
                msg = "Please specify a sitename using --sitename."
                return (False, msg)
        if '.' in sitename:
            sitename = sitename.split('.')[0]
        git_sync_params = {}
        if not os.path.exists(path):
            os.mkdir(path)
        if os.listdir(path):  # dir isn't empty
            git_dir = os.path.join(path, '.git')
            if os.path.exists(aldryn_dot_filename) and os.path.exists(git_dir):
                with open(aldryn_dot_filename, 'r') as fobj:
                    dir_sitename = fobj.read().strip()
                if sitename != dir_sitename:
                    msg = 'This directory is already being synced with the website "%s"' % dir_sitename
                    return (False, msg)
                repo = git.Repo(path)
                last_synced_commit = repo.git.execute(
                    ['git', 'rev-parse', 'develop_bundle/develop'],
                    **extra_git_kwargs)
                git_sync_params['last_synced_commit'] = last_synced_commit
            else:
                msg = ('The folder you selected is not empty. '
                       'Please choose an empty folder to sync your files.')
                return (False, msg)
        else:
            g = git.Git(path)
            g.execute(['git', 'init'], **extra_git_kwargs)
            repo = git.Repo(path)
            cfg = repo.config_writer()
            cfg.set_value('user', 'name', 'Git Sync by')
            cfg.set_value('user', 'email', self.get_login())
            cfg.write()
            cfg._lock._release_lock()
            del cfg

        if not self._acquire_sync_lock(path):
            if self.interactive:
                if not cli_confirm(
                        'Are you sure you want to start syncing anyway?',
                        message='It seems that you are already syncing this directory.',
                        default=False):
                    return (False, 'Aborted')
            else:
                if force:
                    pass
                else:
                    return (False, Client.DIRECTORY_ALREADY_SYNCING_MESSAGE)

        try:
            response = self.session.get(
                '/api/v1/git-sync/%s/' % sitename, params=git_sync_params, stream=True,
                headers={'accept': 'application/octet'})
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            self._remove_sync_lock(path)
            return (False, Client.NETWORK_ERROR_MESSAGE)

        upstream_modified = True
        if response.status_code == 304:
            upstream_modified = False
        elif response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            if response.status_code < 500:
                msgs.append(response.content)
            self._remove_sync_lock(path)
            return (False, '\n'.join(msgs))

        if upstream_modified:
            git_pull_develop_bundle(response, repo. path)
        git_update_gitignore(repo, ['.*', '!.gitignore', '/db_dumps/'])

        protected_files_filename = os.path.join(
            path, Client.PROTECTED_FILES_FILENAME)
        protected_files = []
        #if (os.path.exists(protected_files_filename)):
        #    with open(protected_files_filename, 'r') as fobj:
        #        protected_files = json.loads(fobj.read())
        ## making the protected files read-only
        #for rel_protected_path in protected_files:
        #    protected_path = os.path.join(path, rel_protected_path)
        #    mode = os.stat(protected_path)[stat.ST_MODE]
        #    read_only_mode = mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH
        #    os.chmod(protected_path, read_only_mode)

        # successfully initialized the sync, saving the site's name
        with open(aldryn_dot_filename, 'w') as fobj:
            fobj.write(sitename)

        upstream_remote = repo.remotes.develop_bundle
        last_synced_commit = upstream_remote.refs.develop.commit.hexsha

        sync_handler = GitSyncHandler(
            self, sitename, repo, last_synced_commit,
            network_error_callback, sync_error_callback,
            protected_files, protected_file_change_callback,
            relpath=path, sync_indicator_callback=sync_indicator_callback)
        sync_handler.start()
        self._sync_handlers_cache[sitename] = sync_handler
        if self.interactive:
            print "Done, now watching for changes. You can stop the sync by hitting Ctrl-c in this shell"

            try:
                while self._is_syncing(sitename):
                    time.sleep(1)
            except KeyboardInterrupt:
                sync_handler.stop()
            return (True, 'Stopped syncing')
        else:
            return (True, sync_handler)

    def _is_syncing(self, sitename):
        return sitename in self._sync_handlers_cache

    def sites(self):
        try:
            response = self.session.get('/api/v1/sites/', stream=True)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return (False, Client.NETWORK_ERROR_MESSAGE)
        if response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            if response.status_code < 500:
                msgs.append(response.content)
            return (False, '\n'.join(msgs))
        else:
            sites = json.loads(response.content)
            if self.interactive:
                data = json.dumps(sites, sort_keys=True, indent=4, separators=(',', ': '))
            else:
                data = sites
            return (True, data)

    def newest_version(self):
        try:
            response = self.session.get('/api/v1/newest-client-app-version/')
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return (False, Client.NETWORK_ERROR_MESSAGE)
        if response.status_code == 404:
            return (True, None)
        elif response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            if response.status_code < 500:
                msgs.append(response.content)
            return (False, '\n'.join(msgs))
        else:
            version = json.loads(response.content)
            return (True, version)
