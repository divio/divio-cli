# -*- coding: utf-8 -*-
import getpass
import shutil
import tarfile
import os
import urlparse
import netrc
import time

import requests
try:
    from watchdog.observers.kqueue import KqueueObserver as Observer
except ImportError:
    from watchdog.observers import Observer
import yaml

from cmscloud_client.serialize import register_yaml_extensions, Trackable, File
from cmscloud_client.sync import SyncEventHandler
from cmscloud_client.utils import (validate_boilerplate_config, bundle_boilerplate, filter_template_files,
                                   filter_static_files, validate_app_config, bundle_app)


class WritableNetRC(netrc.netrc):
    def __init__(self, *args, **kwargs):
        home = os.path.expanduser("~")
        netrc_path = os.path.join(home, ".netrc")
        if not os.path.exists(netrc_path):
            open(netrc_path, 'a').close()
            os.chmod(netrc_path, 0600)
        netrc.netrc.__init__(self, *args, **kwargs)

    def add(self, host, login, account, password):
        self.hosts[host] = (login, account, password)

    def write(self, path=None):
        if path is None:
            path = os.path.join(os.environ['HOME'], '.netrc')
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

    def __init__(self, host):
        register_yaml_extensions()
        self.host = urlparse.urlparse(host)[1]
        self.netrc = WritableNetRC()
        auth_data = self.netrc.hosts.get(self.host)
        if auth_data:
            headers = {
                'Authorization': 'Basic %s' % auth_data[2]
            }
        else:
            headers = {}
        self.session = SingleHostSession(host, headers=headers, trust_env=False)

    def login(self):
        email = raw_input('E-Mail: ')
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
            msg = "Could not log in, invalid email or password"
            return (False, msg)
        else:
            msg = ''
            if response.content:
                msg += response.content + '\n'
            msg += "There was a problem logging in, please try again later."
            return (False, msg)

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
                                     static=filter_static_files)
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

    def sync(self, sitename=None, path='', interactive=True):
        cmscloud_dot_filename = os.path.join(path, Client.CMSCLOUD_DOT_FILENAME)
        if not sitename:
            if os.path.exists(cmscloud_dot_filename):
                with open('.cmscloud', 'r') as fobj:
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
                print "Aborted"
                return True
            elif answer.lower() == 'y':
                break
            else:
                print "Invalid answer, please type either y or n"

        for folder in ['static', 'templates']:
            if os.path.exists(folder):
                if os.path.isdir(folder):
                    shutil.rmtree(folder)
                else:
                    os.remove(folder)
        print "Updating local files..."
        response = self.session.get('/api/v1/sync/%s/' % sitename, stream=True)
        if response.status_code != 200:
            msgs = []
            msgs.append("Unexpected HTTP Response %s" % response.status_code)
            msgs.append(response.content)
            return (False, '\n'.join(msgs))
        tarball = tarfile.open(mode='r|gz', fileobj=response.raw)
        tarball.extractall()
        with open(cmscloud_dot_filename, 'w') as fobj:
            fobj.write(sitename)

        if interactive:
            print "Done, now watching for changes. You can stop the sync by hitting Ctrl-c in this shell"

            event_handler = SyncEventHandler(self.session, sitename)
            observer = Observer()
            observer.schedule(event_handler, '.', recursive=True)
            observer.start()

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()
            msg = "Stopped syncing"
            return (True, msg)
        else:
            msg = "Successfully synced application"
            return (True, msg)
