# -*- coding: utf-8 -*-
import getpass
import json
import netrc
import os
import shutil
import tarfile
import time
import urlparse

import requests
from watchdog.observers import Observer
import yaml

from cmscloud_client.serialize import register_yaml_extensions, Trackable, File
from cmscloud_client.sync import SyncEventHandler
from cmscloud_client.utils import (
    validate_boilerplate_config, bundle_boilerplate, filter_template_files,
    filter_static_files, validate_app_config, bundle_app, filter_sass_files)


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = os.sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)

CACERT_PEM_PATH = resource_path('cacert.pem')


class WritableNetRC(netrc.netrc):
    def __init__(self, *args, **kwargs):
        netrc_path = self.get_netrc_path()
        if not os.path.exists(netrc_path):
            open(netrc_path, 'a').close()
            os.chmod(netrc_path, 0600)
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
    APP_FILENAME = 'app.yaml'
    BOILERPLATE_FILENAME = 'boilerplate.yaml'
    CMSCLOUD_CONFIG_FILENAME = 'cmscloud_config.py'
    CMSCLOUD_DOT_FILENAME = '.cmscloud'
    CMSCLOUD_HOST_DEFAULT = 'https://control.django-cms.com'
    CMSCLOUD_HOST_KEY = 'CMSCLOUD_HOST'
    DATA_FILENAME = 'data.yaml'
    SETUP_FILENAME = 'setup.py'

    ALL_CONFIG_FILES = [APP_FILENAME, BOILERPLATE_FILENAME, CMSCLOUD_CONFIG_FILENAME, SETUP_FILENAME, DATA_FILENAME]

    def __init__(self, host):
        register_yaml_extensions()
        self.host = urlparse.urlparse(host)[1]
        self.netrc = WritableNetRC()
        auth_data = self.get_auth_data()
        if auth_data:
            headers = {
                'Authorization': 'Basic %s' % auth_data[2]
            }
        else:
            headers = {}
        self.session = SingleHostSession(host, headers=headers, trust_env=False)

    def get_auth_data(self):
        return self.netrc.hosts.get(self.host)

    def is_logged_in(self):
        auth_data = self.get_auth_data()
        return bool(auth_data)

    def get_login(self):
        if self.is_logged_in():
            auth_data = self.get_auth_data()
            return auth_data[0]

    def logout(self, interactive=True):
        while interactive:
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
        response = self.session.post('/api/v1/login/', data={'email': email, 'password': password})
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

    def upload_boilerplate(self, path=''):
        boilerplate_filename = os.path.join(path, Client.BOILERPLATE_FILENAME)
        data_filename = os.path.join(path, Client.DATA_FILENAME)

        if not os.path.exists(boilerplate_filename):
            msg = "File '%s' not found." % boilerplate_filename
            return (False, msg)
        extra_file_paths = []
        with open(boilerplate_filename) as fobj:
            with Trackable.tracker as extra_objects:
                config = yaml.safe_load(fobj)
                if os.path.exists(data_filename):
                    with open(data_filename) as fobj2:
                        data = yaml.safe_load(fobj2)
                else:
                    data = {}
                extra_file_paths.extend([f.path for f in extra_objects[File]])
        if not validate_boilerplate_config(config):
            return False
        tarball = bundle_boilerplate(config, data, extra_file_paths, templates=filter_template_files,
                                     static=filter_static_files, private=filter_sass_files)
        response = self.session.post('/api/v1/boilerplates/', files={'boilerplate': tarball})
        msg = '\t'.join([str(response.status_code), response.content])
        return (True, msg)

    def validate_boilerplate(self, path=''):
        boilerplate_filename = os.path.join(path, Client.BOILERPLATE_FILENAME)

        if not os.path.exists(boilerplate_filename):
            msg = "File '%s' not found." % boilerplate_filename
            return (False, msg)
        with open(boilerplate_filename) as fobj:
            config = yaml.safe_load(fobj)
        return validate_boilerplate_config(config)

    def upload_app(self, path=''):
        app_filename = os.path.join(path, Client.APP_FILENAME)
        cmscloud_config_filename = os.path.join(path, Client.CMSCLOUD_CONFIG_FILENAME)
        setup_filename = os.path.join(path, Client.SETUP_FILENAME)
        msgs = []
        if not os.path.exists(setup_filename):
            msg = "File '%' not found." % Client.SETUP_FILENAME
            return (False, msg)
        if not os.path.exists(app_filename):
            msg = "File '%s' not found." % app_filename
            return (False, msg)
        with open(app_filename) as fobj:
            config = yaml.safe_load(fobj)
        (valid, msg) = validate_app_config(config)
        if not valid:
            return (False, msg)
        if os.path.exists(cmscloud_config_filename):
            with open(cmscloud_config_filename) as fobj:
                script = fobj.read()
        else:
            script = ''
            msgs.append("File '%s' not found, your app will not have any configurable settings." %
                        Client.CMSCLOUD_CONFIG_FILENAME)
        tarball = bundle_app(config, script)
        response = self.session.post('/api/v1/apps/', files={'app': tarball})
        msgs.append('\t'.join([str(response.status_code), response.content]))
        return (True, '\n'.join(msgs))

    def validate_app(self, path=''):
        app_filename = os.path.join(path, Client.APP_FILENAME)
        setup_filename = os.path.join(path, Client.SETUP_FILENAME)
        if not os.path.exists(setup_filename):
            msg = "File '%s' not found." % Client.SETUP_FILENAME
            return (False, msg)
        if not os.path.exists(app_filename):
            msg = "File '%s' not found." % Client.APP_FILENAME
            return (False, msg)
        with open(app_filename) as fobj:
            config = yaml.safe_load(fobj)
        return validate_app_config(config)

    def sync(self, sitename=None, path='.', interactive=True):
        cmscloud_dot_filename = os.path.join(path, Client.CMSCLOUD_DOT_FILENAME)
        if not sitename:
            if os.path.exists(cmscloud_dot_filename):
                with open(cmscloud_dot_filename, 'r') as fobj:
                    sitename = fobj.read().strip()
            if not sitename:
                msg = "Please specify a sitename using --sitename."
                return (False, msg)
        if '.' in sitename:
            sitename = sitename.split('.')[0]
        print "Preparing to sync %s." % sitename
        print "This will undo all local changes."
        while interactive:
            answer = raw_input('Are you sure you want to continue? [yN]')
            if answer.lower() == 'n' or not answer:
                msg = "Aborted"
                return (True, msg)
            elif answer.lower() == 'y':
                break
            else:
                print "Invalid answer, please type either y or n"

        for folder in ['static', 'templates', 'private']:
            folder_path = os.path.join(path, folder)
            if os.path.exists(folder_path):
                if os.path.isdir(folder_path):
                    shutil.rmtree(folder_path)
                else:
                    os.remove(folder_path)
        print "Updating local files..."
        response = self.session.get('/api/v1/sync/%s/' % sitename, stream=True,
                                    headers={'accept': 'application/octet'})
        if response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            if response.status_code < 500:
                msgs.append(response.content)
            return (False, '\n'.join(msgs))
        tarball = tarfile.open(mode='r|gz', fileobj=response.raw)
        tarball.extractall(path=path)
        tarball.close()
        with open(cmscloud_dot_filename, 'w') as fobj:
            fobj.write(sitename)

        event_handler = SyncEventHandler(self.session, sitename, relpath=path)
        observer = Observer()
        observer.event_queue.queue.clear()
        observer.schedule(event_handler, path, recursive=True)
        observer.start()

        if interactive:
            print "Done, now watching for changes. You can stop the sync by hitting Ctrl-c in this shell"

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()
            msg = "Stopped syncing"
            return (True, msg)
        else:
            return (True, observer)

    def sites(self, interactive=True):
        response = self.session.get('/api/v1/sites/', stream=True)
        if response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            if response.status_code < 500:
                msgs.append(response.content)
            return (False, '\n'.join(msgs))
        else:
            sites = json.loads(response.content)
            if interactive:
                data = json.dumps(sites, sort_keys=True, indent=4, separators=(',', ': '))
            else:
                data = sites
            return (True, data)
