# -*- coding: utf-8 -*-
from watchdog.events import FileSystemEventHandler
from cmscloud_client.utils import is_valid_file_name
import os


def relpath(path):
    return os.path.relpath(path, '.')


class SyncEventHandler(FileSystemEventHandler):
    def __init__(self, session, sitename):
        self.session = session
        self.sitename = sitename

    def _send_request(self, method, *args, **kwargs):
        response = self.session.request(method, '/api/v1/sync/%s/' % self.sitename, *args, **kwargs)
        if not response.ok:
            if response.status_code == 400:
                print "Sync failed! %s" % response.content
            else:
                print "Sync failed! Unexpected status code %s" % response.status_code
                print response.content

    def on_moved(self, event):
        base_dest = os.path.basename(event.dest_path)
        if event.is_directory:
            if base_dest.startswith('.'):
                return
            print "Syncing directory move from %s to %s" % (event.src_path, event.dest_path)
            self._send_request('PUT', data={'source': relpath(event.src_path), 'path': relpath(event.dest_path)})
        else:
            if is_valid_file_name(base_dest):
                print "Syncing file move from %s to %s" % (event.src_path, event.dest_path)
                self._send_request('PUT', data={'source': relpath(event.src_path), 'path': relpath(event.dest_path)})

    def on_created(self, event):
        if event.is_directory:
            return
        if is_valid_file_name(os.path.basename(event.src_path)):
            print "Syncing file creation %s" % event.src_path
            self._send_request('POST', data={'path': relpath(event.src_path)}, files={'content': open(event.src_path)})

    def on_deleted(self, event):
        base_src = os.path.basename(event.src_path)
        if event.is_directory:
            if base_src.startswith('.'):
                return
            print "Syncing directory deletion %s" % event.src_path
            self._send_request('DELETE', data={'path': relpath(event.src_path)})
        else:
            if is_valid_file_name(base_src):
                print "Syncing file deletion %s" % event.src_path
                self._send_request('DELETE', params={'path': relpath(event.src_path)})

    def on_modified(self, event):
        if event.is_directory:
            return
        if is_valid_file_name(os.path.basename(event.src_path)):
            print "Syncing file modification %s" % event.src_path
            self._send_request('PUT', data={'path': relpath(event.src_path)}, files={'content': open(event.src_path)})
