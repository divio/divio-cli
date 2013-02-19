# -*- coding: utf-8 -*-
import getpass
import logging
import urlparse
import netrc
import time
import sys

from cmscloud_client.serialize import register_yaml_extensions, Trackable, File
from cmscloud_client.sync import SyncEventHandler
from cmscloud_client.utils import validate_boilerplate_config, bundle_boilerplate, filter_template_files, filter_static_files, validate_app_config, bundle_app
import os
import requests
from watchdog.events import LoggingEventHandler
from watchdog.observers import Observer
import yaml


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
            print "Logged in as %s" % email
            return True
        elif response.status_code == requests.codes.forbidden:
            print "Could not log in, invalid email or password"
            return False
        else:
            print response.content
            print "There was a problem logging in, please try again later."
            return False

    def upload_boilerplate(self):
        if not os.path.exists('boilerplate.yaml'):
            print "File 'boilerplate.yaml' not found."
            return False
        extra_file_paths = []
        with open('boilerplate.yaml') as fobj:
            with Trackable.tracker as extra_objects:
                config = yaml.safe_load(fobj)
                if os.path.exists('data.yaml'):
                    with open('data.yaml') as fobj2:
                        data = yaml.safe_load(fobj2)
                else:
                    data = {}
                extra_file_paths.extend([f.path for f in extra_objects[File]])
        if not validate_boilerplate_config(config):
            return False
        tarball = bundle_boilerplate(config, data, extra_file_paths, templates=filter_template_files,
                                     static=filter_static_files)
        response = self.session.post('/api/v1/boilerplates/', files={'boilerplate': tarball})
        print response.status_code, response.content
        return True

    def validate_boilerplate(self):
        if not os.path.exists('boilerplate.yaml'):
            print "File 'boilerplate.yaml' not found."
            return False
        with open('boilerplate.yaml') as fobj:
            config = yaml.safe_load(fobj)
        return validate_boilerplate_config(config)

    def upload_app(self):
        if not os.path.exists('setup.py'):
            print "File 'setup.py' not found."
            return False
        if not os.path.exists('app.yaml'):
            print "File 'app.yaml' not found."
            return False
        with open('app.yaml') as fobj:
            config = yaml.safe_load(fobj)
        if not validate_app_config(config):
            return False
        if os.path.exists('cmscloud_config.py'):
            with open('cmscloud_config.py') as fobj:
                script = fobj.read()
        else:
            script = ''
            print "File 'cmscloud_config.py' not found, your app will not have any configurable settings."
        tarball = bundle_app(config, script)
        response = self.session.post('/api/v1/apps/', files={'app': tarball})
        print response.status_code, response.content
        return True

    def validate_app(self):
        if not os.path.exists('setup.py'):
            print "File 'setup.py' not found."
            return False
        if not os.path.exists('app.yaml'):
            print "File 'app.yaml' not found."
            return False
        with open('app.yaml') as fobj:
            config = yaml.safe_load(fobj)
        return validate_app_config(config)

    def static_sync(self):
        if not os.path.exists('.cmscloud'):
            print "File '.cmscloud' not found."
            return False
        with open('.cmscloud') as fobj:
            config = yaml.safe_load(fobj)
        site = config['site']
        path = os.getcwd()
        if not site:
            print "site parameter in .cmscloud is missing"
            print "example:"
            print "site: mysite.cloud.django-cms.com"
            return False
        print "Syncing all static files and templates from %s." % site
        print ""
        print "Attention: All local files will be overwritten."
        print ""
        sure = raw_input('Are you sure? (enter to continue): ')
        print "downloading files from %s to %s." % (site, path)
        time.sleep(1)
        print "watching directory %s for changes. Hit ctrl-c for aborting." % path
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        event_handler = SyncEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()







