# -*- coding: utf-8 -*-
from SimpleHTTPServer import SimpleHTTPRequestHandler, BaseHTTPServer
import posixpath
import os
import urllib


def static_handler_factory(directory_mapping):

    class StaticHandler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            if path.startswith('/'):
                path = path[1:]
            site_name, path = path.split('/', 1)
            site_name = urllib.unquote(site_name)
            # abandon query parameters
            path = path.split('?', 1)[0]
            path = path.split('#', 1)[0]
            path = posixpath.normpath(urllib.unquote(path))
            words = path.split('/')
            words = filter(None, words)
            path = directory_mapping[site_name]['dir']
            for word in words:
                drive, word = os.path.splitdrive(word)
                head, word = os.path.split(word)
                path = os.path.join(path, word)
            return path

    return StaticHandler


def get_static_server(port, directory_mapping):
    server_address = ('', port)
    StaticHandlerClass = static_handler_factory(directory_mapping)
    ServerClass = BaseHTTPServer.HTTPServer
    httpd = ServerClass(server_address, StaticHandlerClass)
    return httpd
