# -*- coding: utf-8 -*-
from collections import deque
from operator import attrgetter
import Queue
import datetime
import os
import threading

from watchdog.events import (
    EVENT_TYPE_CREATED, EVENT_TYPE_DELETED, EVENT_TYPE_MODIFIED,
    EVENT_TYPE_MOVED, FileModifiedEvent)

from cmscloud_client.utils import (
    ValidationError, hashfile, is_hidden, is_valid_file_name, uniform_filepath)


class SyncEvent(object):
    def __init__(self, event, timestamp, relpath):
        self._event = event
        self.timestamp = timestamp
        self.relpath = relpath

        from cmscloud_client.sync import SYNCABLE_DIRECTORIES
        for attr in ['src', 'dest']:
            if hasattr(event, '%s_path' % attr):
                event_path = getattr(event, '%s_path' % attr)
                if event_path is None:
                    # Some file managers don't set src_path while restoring
                    # the file/directory from the trash
                    setattr(self, '_sync_%s' % attr, False)
                    error_msg = 'Invalid event: %s' % event
                    setattr(self, '_sync_%s_error' % attr, error_msg)
                    continue
                event_rel_path = os.path.relpath(event_path, relpath)
                setattr(self, '_rel_%s_path' % attr, event_rel_path)
                event_base_path = os.path.basename(event_path)
                setattr(self, '_base_%s_path' % attr, event_base_path)
                sync_dir = event_rel_path.startswith(SYNCABLE_DIRECTORIES)
                if not sync_dir:
                    syncable = False
                    error_msg = ('Not in the syncable directory: %s' %
                                 (', '.join(SYNCABLE_DIRECTORIES)))
                    setattr(self, '_sync_%s_error' % attr, error_msg)
                elif is_hidden(event_base_path):
                    syncable = False
                    name = 'directories' if event.is_directory else 'files'
                    error_msg = 'Hidden %s aren\'t synchronized.' % name
                    setattr(self, '_sync_%s_error' % attr, error_msg)
                elif event.is_directory:
                    syncable = True
                else:
                    try:
                        syncable = is_valid_file_name(event_base_path)
                    except ValidationError as e:
                        syncable = False
                        setattr(self, '_sync_%s_error' % attr, e.message)
                setattr(self, '_sync_%s' % attr, syncable)

    def __repr__(self):
        return ('<%(class_name)s: event=%(event)s, %(timestamp)s>' %
                {'class_name': self.__class__.__name__,
                 'event': repr(self._event),
                 'timestamp': repr(self.timestamp)})

    # mirroring properties of the underlying event
    @property
    def src_path(self):
        return getattr(self._event, 'src_path', None)

    @property
    def dest_path(self):
        return getattr(self._event, 'dest_path', None)

    @property
    def event_type(self):
        return self._event.event_type

    @property
    def is_directory(self):
        return self._event.is_directory

    # end of event's properties

    @property
    def rel_src_path(self):
        return getattr(self, '_rel_src_path', None)

    @property
    def base_src_path(self):
        return getattr(self, '_base_src_path', None)

    @property
    def rel_dest_path(self):
        return getattr(self, '_rel_dest_path', None)

    @property
    def base_dest_path(self):
        return getattr(self, '_base_dest_path', None)

    @property
    def is_src_path_syncable(self):
        return getattr(self, '_sync_src', False)

    @property
    def not_syncable_src_path_reason(self):
        return getattr(self, '_sync_src_error', None)

    @property
    def is_dest_path_syncable(self):
        return getattr(self, '_sync_dest', False)

    @property
    def not_syncable_dest_path_reason(self):
        return getattr(self, '_sync_dest_error', None)

    def prepare_request(self):
        event_type = self.event_type
        if event_type == EVENT_TYPE_CREATED:
            msg = "Syncing file creation %s" % self.src_path
            method = 'POST'
            kwargs = {'data': {'path': self.rel_src_path},
                      'files': {'content': open(self.src_path)}}
        elif event_type == EVENT_TYPE_MODIFIED:
            msg = "Syncing file modification %s" % self.src_path
            method = 'PUT'
            kwargs = {'data': {'path': self.rel_src_path},
                      'files': {'content': open(self.src_path)}}
        elif event_type == EVENT_TYPE_MOVED:
            msg = "Syncing file move from %s to %s" % (
                self.src_path, self.dest_path)
            method = 'PUT'
            kwargs = {
                'data': {'source': self.rel_src_path,
                         'path': self.rel_dest_path}}
        elif event_type == EVENT_TYPE_DELETED:
            msg = "Syncing file deletion %s" % self.src_path
            method = 'DELETE'
            if self.is_directory:
                rel_src_path = self.rel_src_path
                if not rel_src_path.endswith(os.sep):
                    rel_src_path += os.sep
            else:
                rel_src_path = self.rel_src_path
            kwargs = {'params': {'path': rel_src_path}}
        return (msg, method, kwargs)


class EventsBuffer(object):
    def __init__(self, relpath):
        self.relpath = relpath

        self._events_filepaths = set()
        self._created_events = {}
        self._modified_events = {}
        self._moved_events = {}
        self._deleted_events = {}
        self._events_lock = threading.Lock()

    def set_created_event(self, sync_event):
        filepath = uniform_filepath(sync_event.src_path)
        with self._events_lock:
            self._events_filepaths.add(filepath)
            self._created_events[filepath] = sync_event

    def set_modified_event(self, sync_event):
        filepath = uniform_filepath(sync_event.src_path)
        with self._events_lock:
            self._events_filepaths.add(filepath)
            self._modified_events[filepath] = sync_event

    def set_moved_event(self, sync_event):
        filepath = uniform_filepath(sync_event.src_path)
        with self._events_lock:
            self._events_filepaths.add(filepath)
            self._moved_events[filepath] = sync_event

    def set_deleted_event(self, sync_event):
        filepath = uniform_filepath(sync_event.src_path)
        with self._events_lock:
            self._events_filepaths.add(filepath)
            self._deleted_events[filepath] = sync_event

    def filter_out_oldest_events_buffer(self, older_than_seconds):
        with self._events_lock:
            old_ev_buf = EventsBuffer(self.relpath)
            filtered_events_filepaths = set()
            now_timestamp = datetime.datetime.now()
            for src, dest in [
                    (self._created_events, old_ev_buf._created_events),
                    (self._modified_events, old_ev_buf._modified_events),
                    (self._moved_events, old_ev_buf._moved_events),
                    (self._deleted_events, old_ev_buf._deleted_events)]:
                for k in src.keys():
                    sync_event = src[k]
                    event_age = now_timestamp - sync_event.timestamp
                    if event_age.total_seconds() >= older_than_seconds:
                        dest[k] = sync_event
                        old_ev_buf._events_filepaths.add(k)
                        del src[k]
                    else:
                        filtered_events_filepaths.add(k)
            self._events_filepaths = filtered_events_filepaths
        return old_ev_buf

    def log_state(self, logger):
        with self._events_lock:
            if self._created_events:
                logger.debug(
                    'raw "created" events:\t' + repr(self._created_events.values()))
            if self._modified_events:
                logger.debug(
                    'raw "modified" events:\t' + repr(self._modified_events.values()))
            if self._moved_events:
                logger.debug(
                    'raw "moved" events:\t' + repr(self._moved_events.values()))
            if self._deleted_events:
                logger.debug(
                    'raw "deleted" events:\t' + repr(self._deleted_events.values()))

    def get_reduced_events_list(self, is_modified_checker, logger):
        '''
        Reducing the number of requests by merging events that originated from
        a complex action e.g.:
            - directory move,
            - "save to copy, remove original file and move copy to
              the original filename" saving strategy,
        '''

        with self._events_lock:
            sync_events = []
            for filepath in self._events_filepaths:
                created = self._created_events.get(filepath, None)
                modified = self._modified_events.get(filepath, None)
                moved = self._moved_events.get(filepath, None)
                deleted = self._deleted_events.get(filepath, None)

                if deleted and created:
                    # Due to the watchdog's implementation of the file system's
                    # observers we cannot rely on the order of consequent
                    # events as they could be received in a single batch and
                    # put into the queue in an arbitrary order. Therefor the
                    # only sure option is to check if the file exists.
                    if os.path.exists(filepath):
                        # "save to copy, delete original, rename" case
                        # The file actually was modified, so we remove the
                        # 'deleted' event and send only the 'modified' one
                        # or change the 'created' into it
                        deleted = None
                        if modified:
                            created = None
                        else:
                            raw_modified_event = FileModifiedEvent(
                                created.src_path)
                            modified = SyncEvent(
                                raw_modified_event, created.timestamp, created.relpath)
                            created = None
                    else:
                        # Sending only the deleted event.
                        # Even if the file was quickly created and then deleted
                        # the 'delete request' will gracefully return a warning
                        created = None
                        modified = None
                        moved = None

                if created and modified:
                    # The file was truly created not 'saved-by-moving-a-copy',
                    # the modified event is unnecessary.
                    modified = None

                def parent_event_exist(filepath, parent_events):
                    event_exist = False
                    parent_dir = os.path.dirname(filepath)
                    parent_dir = uniform_filepath(parent_dir)
                    max_depth = 10
                    while max_depth > 0:
                        max_depth -= 1
                        parent_dir = os.path.abspath(parent_dir)
                        if parent_dir in parent_events:
                            event_exist = True
                            break
                        if self.relpath.startswith(parent_dir):
                            # went beyond the syncing directory
                            break
                        parent_dir = os.path.dirname(parent_dir)
                        parent_dir = uniform_filepath(parent_dir)
                    return event_exist

                if moved:
                    # Checking if any of the parent directories were moved
                    # in which case this event is unnecessary.
                    if parent_event_exist(filepath, self._moved_events):
                        moved = None

                if deleted:
                    # Checking if any of the parent directories were deleted
                    # in which case this event is unnecessary.
                    if parent_event_exist(filepath, self._deleted_events):
                        deleted = None

                # Appending reduced events to the result list
                if created:
                    sync_events.append(created)
                if modified:
                    if is_modified_checker(modified.src_path):
                        sync_events.append(modified)
                    else:
                        msg = 'File unchanged: %s' % modified.src_path
                        logger.debug(msg)
                        print msg
                if moved:
                    sync_events.append(moved)
                if deleted:
                    sync_events.append(deleted)

            # restoring the chronological order of the events
            sorted_sync_events = sorted(
                sync_events, key=attrgetter('timestamp'))
            return sorted_sync_events


class ProceededEventsQueue(Queue.Queue):
    def put_event(self, request):
        self.put(request)

    def get_event(self, timeout=None):
        try:
            sync_event = self.get(
                block=True, timeout=timeout)
        except Queue.Empty:
            return None
        else:
            self.task_done()
            return sync_event


class FileHashesCache(dict):
    def __init__(self, relpath):
        self._hashes_lock = threading.Lock()
        self.relpath = relpath

    def update_hash(self, filepath, file_hash=None):
        if file_hash is None:
            with open(filepath) as fd:
                file_hash = hashfile(fd)
        self[filepath] = file_hash

    def update_hashes(self):
        with self._hashes_lock:
            dirs_queue = deque()
            dirs_queue.append(self.relpath)
            while dirs_queue:
                parent_dir = dirs_queue.popleft()
                for filename in os.listdir(parent_dir):
                    filepath = os.path.join(parent_dir, filename)
                    if os.path.isdir(filepath):
                        dirs_queue.append(filepath)
                    else:
                        filepath = uniform_filepath(filepath)
                        self.update_hash(filepath)

    def is_file_changed(self, filepath):
        filepath = uniform_filepath(filepath)
        with open(filepath) as fd:
            file_hash = hashfile(fd)
        with self._hashes_lock:
            previous_file_hash = self.get(filepath, None)
            if file_hash != previous_file_hash:
                self.update_hash(filepath, file_hash=file_hash)
                status = True
            else:
                status = False
        return status
