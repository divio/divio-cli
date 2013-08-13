# -*- coding: utf-8 -*-
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent
from cmscloud_client.utils import is_valid_file_name
import os


def relpath(path, start):
    return os.path.relpath(path, start)


class SyncEventHandler(FileSystemEventHandler):
    def __init__(self, session, sitename, relpath='.'):
        self.session = session
        self.sitename = sitename
        self.relpath = relpath

    def dispatch(self, event):
        for attr in ['src', 'dest']:
            if hasattr(event, '%s_path' % attr):
                event_rel_path = relpath(getattr(event, '%s_path' % attr), self.relpath)
                setattr(event, 'rel_%s_path' % attr, event_rel_path)
                event_base_path = os.path.basename(getattr(event, '%s_path' % attr))
                setattr(event, 'base_%s_path' % attr, event_base_path)
                sync_dir = event_rel_path.startswith(('templates/', 'static/'))
                if event.is_directory:
                    syncable = sync_dir and not event_base_path.startswith('.')
                else:
                    syncable = sync_dir and is_valid_file_name(event_base_path)
                setattr(event, 'sync_%s' % attr, syncable)
        super(SyncEventHandler, self).dispatch(event)

    def _send_request(self, method, *args, **kwargs):
        response = self.session.request(method, '/api/v1/sync/%s/' % self.sitename, *args, **kwargs)
        if not response.ok:
            if response.status_code == 400:
                print "Sync failed! %s" % response.content
            else:
                print "Sync failed! Unexpected status code %s" % response.status_code
                print response.content

    def on_moved(self, event):
        if event.is_directory:
            self.on_dir_moved(event)
        else:
            self.on_file_moved(event)

    def on_dir_moved(self, event):
        if event.sync_src:
            if event.sync_dest:
                print "Syncing directory move from %s to %s" % (event.src_path, event.dest_path)
                self._send_request('PUT', data={'source': event.rel_src_path, 'path': event.rel_dest_path})
            else:
                # moved OUTSIDE syncable areas, remove!
                self.on_deleted(event)
        elif event.sync_dest:
            # source isn't in sync area, but dest is, so create the stuff
            create_event = DirCreatedEvent(event.dest_path)
            self.on_created(create_event)

    def on_file_moved(self, event):
        if event.sync_src:
            if event.sync_dest:
                print "Syncing file move from %s to %s" % (event.src_path, event.dest_path)
                self._send_request('PUT', data={'source': event.rel_src_path, 'path': event.rel_dest_path})
            else:
                # moved outside sync, remove
                self.on_deleted(event)
        elif event.sync_dest:
            # moved inside sync, create
            create_event = FileCreatedEvent(event.dest_path)
            self.dispatch(create_event)

    def on_created(self, event):
        if event.is_directory:
            # check if it has content, if so create stuff
            for thing in os.listdir(event.src_path):
                create_event = FileCreatedEvent(os.path.join(event.src_path, thing))
                self.dispatch(create_event)
        elif event.sync_src:
            print "Syncing file creation %s" % event.src_path
            self._send_request('POST', data={'path': event.rel_src_path}, files={'content': open(event.src_path)})

    def on_deleted(self, event):
        # TODO fix race condition
        if os.path.exists(event.src_path): # hack for OSX
            return self.on_modified(event)
        if not event.sync_src:
            return
        if event.is_directory:
            print "Syncing directory deletion %s" % event.src_path
            self._send_request('DELETE', data={'path': event.rel_src_path})
        else:
            print "Syncing file deletion %s" % event.src_path
            self._send_request('DELETE', params={'path': event.rel_src_path})

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.sync_src:
            print "Syncing file modification %s" % event.src_path
            self._send_request('PUT', data={'path': event.rel_src_path}, files={'content': open(event.src_path)})
