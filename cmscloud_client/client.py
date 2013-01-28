# -*- coding: utf-8 -*-
import getpass
import urlparse
from cmscloud_client.serialize import register_yaml_extensions, Trackable, File
from cmscloud_client.utils import validate_boilerplate_config, bundle_boilerplate, filter_template_files, filter_static_files, validate_app_config, bundle_app
import os
import requests
import netrc
from requests.auth import AuthBase
import yaml


class WritableNetRC(netrc.netrc):
    def add(self, host, login, account, password):
        self.hosts[host] = (login, account, password)

    def write(self, path=None):
        if path is None:
            path =  os.path.join(os.environ['HOME'], '.netrc')
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


class BasicTokenAuth(AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers['Authorization'] = 'Basic %s' % self.token
        return r


class SingleHostSession(requests.Session):
    def __init__(self, host, **kwargs):
        self.host = host.rstrip('/')
        super(SingleHostSession, self).__init__(**kwargs)

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
            auth = BasicTokenAuth(auth_data[2])
        else:
            auth = None
        self.session = SingleHostSession(host, auth=auth)

    def login(self):
        email = raw_input('E-Mail: ')
        password = getpass.getpass('Password: ')
        response = self.session.post('/api/v1/login/', data={'email': email, 'password': password})
        if response.ok:
            token = response.content
            self.session.auth = BasicTokenAuth(token)
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
        tarball = bundle_boilerplate(config, data, extra_file_paths, templates=filter_template_files, static=filter_static_files)
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
        print response.content
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

