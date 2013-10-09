# -*- coding: utf-8 -*-
from threading import Lock, Thread
import datetime
import os
import time

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent
from cmscloud_client.utils import hashfile, is_valid_file_name


def relpath(path, start):
    return os.path.relpath(path, start)


# Amount of seconds for which the 'on_deleted' event is postponed to wait for
# eventual 'on_created' event (some editors create a new file before saving
# and just remove the old one and rename the new, which we want to treat as
# a 'modified' event.
DELETE_DELAY = 1.0  # seconds

# Amount of time during which we assume that if the newly created file was
# was deleted it was in fact the "rename saving strategy"
TIME_DELTA = datetime.timedelta(0, 1)  # 1 second


class SyncEventHandler(FileSystemEventHandler):

    def __init__(self, session, sitename, relpath='.'):
        self.session = session
        self.sitename = sitename
        self.relpath = relpath

        self._recently_created = {}
        self._recently_deleted = {}
        self._recently_moved = {}
        self._timestamps_lock = Lock()

        self._recently_modified_file_hashes = {}
        self._hashes_lock = Lock()

    def dispatch(self, event):
        for attr in ['src', 'dest']:
            if hasattr(event, '%s_path' % attr):
                event_rel_path = relpath(getattr(event, '%s_path' % attr), self.relpath)
                setattr(event, 'rel_%s_path' % attr, event_rel_path)
                event_base_path = os.path.basename(getattr(event, '%s_path' % attr))
                setattr(event, 'base_%s_path' % attr, event_base_path)
                sync_dir = event_rel_path.startswith(('templates/', 'static/', 'private/'))
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

    def _is_created_since(self, filepath, since_timestamp):
        with self._timestamps_lock:
            recently_timestamp = self._recently_created.get(filepath, None)
            if recently_timestamp:
                if recently_timestamp - since_timestamp > datetime.timedelta(0):
                    return True
                else:
                    del self._recently_created[filepath]
                    return False
            else:
                return False

    def _is_recently_deleted(self, filepath, now_timestamp):
        with self._timestamps_lock:
            recently_timestamp = self._recently_deleted.get(filepath, None)
            if recently_timestamp:
                if now_timestamp - recently_timestamp < TIME_DELTA:
                    return True
                else:
                    del self._recently_deleted[filepath]
                    return False
            else:
                return False

    def _is_recently_moved(self, filepath, now_timestamp):
        with self._timestamps_lock:
            recently_timestamp = self._recently_moved.get(filepath, None)
            if recently_timestamp:
                if now_timestamp - recently_timestamp < TIME_DELTA:
                    return True
                else:
                    del self._recently_moved[filepath]
                    return False
            else:
                return False

    def _set_recently_created(self, filepath, timestamp):
        with self._timestamps_lock:
            self._recently_created[filepath] = timestamp

    def _set_recently_deleted(self, filepath, timestamp):
        with self._timestamps_lock:
            self._recently_deleted[filepath] = timestamp

    def _set_recently_moved(self, filepath, timestamp):
        with self._timestamps_lock:
            self._recently_moved[filepath] = timestamp

    def on_moved(self, event):
        '''
        Directory move causes firing of the move events of the files and
        subdirectories within it which is unnecessary and erroneous since
        the source directory on the server no longer exists (as it was moved).
        '''
        now_timestamp = datetime.datetime.now()
        filepath = event.src_path
        self._set_recently_moved(filepath, now_timestamp)

        parent_dir = os.path.dirname(filepath.rstrip(os.sep))
        # checking if the parent directory was recently moved in which case
        # this event is unnecessary
        if not self._is_recently_moved(parent_dir, now_timestamp):
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
            now_timestamp = datetime.datetime.now()
            filepath = event.src_path
            self._set_recently_created(filepath, now_timestamp)
            if self._is_recently_deleted(filepath, now_timestamp):
                return self.on_modified(event)
            else:
                print "Syncing file creation %s" % event.src_path
                self._send_request('POST', data={'path': event.rel_src_path}, files={'content': open(event.src_path)})

    def on_deleted(self, event):
        now_timestamp = datetime.datetime.now()
        self._set_recently_deleted(event.src_path, now_timestamp)
        on_deleted_thread = Thread(target=self._on_deleted_callback, args=(event, now_timestamp))
        on_deleted_thread.start()

    def _on_deleted_callback(self, event, timestamp):
        # Wait for eventual process of renaming after saving (performed by
        # some editors) to be finished.
        time.sleep(DELETE_DELAY)

        if os.path.exists(event.src_path):
            if self._is_created_since(event.src_path, timestamp):
                return  # the create event already sent the 'modified' callback
            else:
                return self.on_modified(event)
        if not event.sync_src:
            return
        if event.is_directory:
            rel_src_path = event.rel_src_path
            if not rel_src_path.endswith('/'):
                rel_src_path += '/'
            print "Syncing directory deletion %s" % event.src_path
            self._send_request('DELETE', params={'path': rel_src_path})
        else:
            print "Syncing file deletion %s" % event.src_path
            self._send_request('DELETE', params={'path': event.rel_src_path})

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.sync_src:
            fd = open(event.src_path)
            file_hash = hashfile(fd)
            fd.seek(0)
            with self._hashes_lock:
                previous_file_hash = self._recently_modified_file_hashes.get(event.src_path, None)
                if file_hash != previous_file_hash:
                    self._recently_modified_file_hashes[event.src_path] = file_hash
                    print "Syncing file modification %s" % event.src_path
                    self._send_request('PUT', data={'path': event.rel_src_path}, files={'content': fd})
