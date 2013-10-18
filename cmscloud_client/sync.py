# -*- coding: utf-8 -*-
from collections import namedtuple
from operator import attrgetter
import Queue
import datetime
import logging
import logging.handlers
import os
import threading
import time

from watchdog.events import (
    DirCreatedEvent, EVENT_TYPE_CREATED, EVENT_TYPE_DELETED,
    EVENT_TYPE_MODIFIED, EVENT_TYPE_MOVED, FileCreatedEvent, FileDeletedEvent,
    FileModifiedEvent, FileSystemEventHandler)

from cmscloud_client.utils import (
    ValidationError, hashfile, is_hidden, is_valid_file_name, relpath,
    uniform_filepath)

#******************************************************************************
# Logging configuration
#******************************************************************************
BACKUP_COUNT = 2
FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILENAME = '.sync.log'
MAX_BYTES = 100 * (2 ** 10)  # 100KB

rotating_handler = logging.handlers.RotatingFileHandler(
    LOG_FILENAME, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
formatter = logging.Formatter(FORMAT)
rotating_handler.setFormatter(formatter)
rotating_handler.setLevel(logging.DEBUG)

sync_logger = logging.getLogger('cmscloud_client.sync')
sync_logger.setLevel(logging.DEBUG)
sync_logger.addHandler(rotating_handler)
#******************************************************************************

# Amount of time during which we collect events and perform heuristics
# to reduce the number of requests
TIME_DELTA = datetime.timedelta(0, 0.5)  # 0.5 second
TIME_DELTA_SECONDS = TIME_DELTA.total_seconds()

# Waiting twice as long as it takes to consider subsequent events
# as a single action e.g. directory move, file save (by 'moving/renaming'),
# to collect all actions from a single "batch"
COLLECT_TIME_DELTA = TIME_DELTA * 2


IGNORED_FILES = set(['.cmscloud', '.cmscloud-folder', LOG_FILENAME])
for i in xrange(1, BACKUP_COUNT + 1):
    IGNORED_FILES.add(LOG_FILENAME + ('.%d' % i))

EventStruct = namedtuple('EventStruct', ['timestamp', 'event'])


class SyncEventHandler(FileSystemEventHandler):

    def __init__(self, session, sitename, relpath='.'):
        self.session = session
        self.sitename = sitename
        self.relpath = os.path.abspath(relpath)

        self._recently_modified_file_hashes = {}
        self._hashes_lock = threading.Lock()

        self._created_events = {}
        self._modified_events = {}
        self._moved_events = {}
        self._deleted_events = {}
        self._events_lock = threading.Lock()

        self._events_queue = Queue.Queue()

        self._main_thread = threading.current_thread()

        # Due to the asynchronous nature of the file systems events
        # there should be only one 'sending requests worker'.
        # (e.g. lagging create request followed by a delete one that will fail)
        self._send_requests_thread = threading.Thread(
            target=self._send_requests_worker, name='Requests sender')
        self._send_requests_thread.start()

        self._collect_events_thread = threading.Thread(
            target=self._collect_events_worker, name='Events collector')
        self._collect_events_thread.start()

    def _put_event(self, request):
        self._events_queue.put(request)

    def _get_event(self, timeout=None):
        try:
            event_struct = self._events_queue.get(
                block=True, timeout=timeout)
        except Queue.Empty:
            return None
        else:
            self._events_queue.task_done()
            return event_struct

    def _events_queue_not_empty(self):
        return not self._events_queue.empty()

    def _pending_events(self):
        return (self._created_events or self._modified_events or
                self._moved_events or self._deleted_events)

    def _collect_events_worker(self):
        local_created_events = {}
        local_modified_events = {}
        local_moved_events = {}
        local_deleted_events = {}
        changed_filepaths = set()

        while self._main_thread.isAlive() or self._pending_events():
            start_timestamp = datetime.datetime.now()
            local_created_events.clear()
            local_modified_events.clear()
            local_moved_events.clear()
            local_deleted_events.clear()
            changed_filepaths.clear()

            # CRITICAL SECTION
            # this should be as fast as possible
            with self._events_lock:  # acquiring the lock, might take a while
                now_timestamp = datetime.datetime.now()
                for src, dest in [(self._created_events, local_created_events),
                                  (self._modified_events,
                                   local_modified_events),
                                  (self._moved_events, local_moved_events),
                                  (self._deleted_events, local_deleted_events)]:
                    for k in src.keys():
                        event_struct = src[k]
                        event_timestamp = event_struct.timestamp
                        event_age = now_timestamp - event_timestamp
                        if event_age >= TIME_DELTA:
                            dest[k] = event_struct
                            changed_filepaths.add(k)
                            del src[k]
            # END OF CRITICAL SECTION

            # reducing the number of requests by merging events
            event_structs = []
            for filepath in changed_filepaths:
                created = local_created_events.get(filepath, None)
                modified = local_modified_events.get(filepath, None)
                moved = local_moved_events.get(filepath, None)
                deleted = local_deleted_events.get(filepath, None)

                def parent_event_exist(filepath, events_src):
                    event_exist = False
                    parent_dir = os.path.dirname(filepath)
                    parent_dir = uniform_filepath(parent_dir)
                    max_depth = 10
                    while max_depth > 0:
                        max_depth -= 1
                        parent_dir = os.path.abspath(parent_dir)
                        if parent_dir in events_src:
                            event_exist = True
                            break
                        if self.relpath.startswith(parent_dir):
                            # went beyond the syncing directory
                            break
                        parent_dir = os.path.dirname(parent_dir)
                        parent_dir = uniform_filepath(parent_dir)
                    return event_exist

                if moved:
                    # checking if any of the parent directories were moved
                    # in which case this event is unnecessary
                    if parent_event_exist(filepath, local_moved_events):
                        moved = None

                if created and deleted:
                    created_timestamp = created.timestamp
                    deleted_timestamp = deleted.timestamp
                    if created_timestamp > deleted_timestamp:
                        # "save to copy, delete original, rename" case
                        # the file actually was modified, so we remove the
                        # 'deleted' event and send only the 'modified' or
                        # change the 'created' into one and send it instead
                        deleted = None
                        if modified:
                            created = None
                        else:
                            raw_modified_event = FileModifiedEvent(
                                created.event.src_path)
                            modified_event = self._prepare_event(
                                raw_modified_event)
                            modified = EventStruct(timestamp=created.timestamp,
                                                   event=modified_event)
                            created = None

                if created and modified:
                    # the file was truly created not 'saved-by-moving-a-copy'
                    # so the modified event is unnecessary
                    modified = None

                if deleted:
                    # checking if any of the parent directories were deleted
                    # in which case this event is unnecessary
                    if parent_event_exist(filepath, local_deleted_events):
                        deleted = None

                if created:
                    event_structs.append(created)
                if modified:
                    event_structs.append(modified)
                if moved:
                    event_structs.append(moved)
                if deleted:
                    event_structs.append(deleted)
            # restoring the chronological order of the events
            sorted_event_structs = sorted(event_structs,
                                          key=attrgetter('timestamp'))

            if local_created_events:
                sync_logger.debug(
                    'raw "created" events:\t' + repr(local_created_events.values()))
            if local_modified_events:
                sync_logger.debug(
                    'raw "modified" events:\t' + repr(local_modified_events.values()))
            if local_moved_events:
                sync_logger.debug(
                    'raw "moved" events:\t' + repr(local_moved_events.values()))
            if local_deleted_events:
                sync_logger.debug(
                    'raw "deleted" events:\t' + repr(local_deleted_events.values()))

            for event_struct in sorted_event_structs:
                sync_logger.debug(
                    'pushing event into the queue:\t' + repr(event_struct))
                self._put_event(event_struct)

            stop_timestamp = datetime.datetime.now()
            time_elapsed_delta = stop_timestamp - start_timestamp
            delay = (COLLECT_TIME_DELTA - time_elapsed_delta).total_seconds()
            if delay > 0:
                time.sleep(delay)

    def _prepare_request(self, event):
        event_type = event.event_type
        if event_type == EVENT_TYPE_CREATED:
            msg = "Syncing file creation %s" % event.src_path
            method = 'POST'
            kwargs = {'data': {'path': event.rel_src_path},
                      'files': {'content': open(event.src_path)}}
        elif event_type == EVENT_TYPE_MODIFIED:
            msg = "Syncing file modification %s" % event.src_path
            method = 'PUT'
            kwargs = {'data': {'path': event.rel_src_path},
                      'files': {'content': open(event.src_path)}}
        elif event_type == EVENT_TYPE_MOVED:
            msg = "Syncing file move from %s to %s" % (
                event.src_path, event.dest_path)
            method = 'PUT'
            kwargs = {
                'data': {'source': event.rel_src_path, 'path': event.rel_dest_path}}
        elif event_type == EVENT_TYPE_DELETED:
            msg = "Syncing file deletion %s" % event.src_path
            method = 'DELETE'
            if event.is_directory:
                rel_src_path = event.rel_src_path
                if not rel_src_path.endswith(os.sep):
                    rel_src_path += os.sep
            else:
                rel_src_path = event.rel_src_path
            kwargs = {'params': {'path': rel_src_path}}
        return (msg, method, kwargs)

    def _send_requests_worker(self):
        while self._main_thread.isAlive() or self._events_queue_not_empty():
            event_struct = self._get_event(timeout=TIME_DELTA_SECONDS)
            if event_struct:
                sync_logger.debug(
                    'sending request for event:\t' + repr(event_struct))
                event = event_struct.event
                msg, method, kwargs = self._prepare_request(event)
                print msg
                self._send_request(method, **kwargs)

    def _send_request(self, method, *args, **kwargs):
        headers = kwargs.get('headers', {})
        if 'accept' not in headers:
            headers['accept'] = 'text/plain'
        kwargs['headers'] = headers
        response = self.session.request(
            method, '/api/v1/sync/%s/' % self.sitename, *args, **kwargs)
        if not response.ok:
            if response.status_code == 400:
                print "Sync failed! %s" % response.content
            else:
                print "Sync failed! Unexpected status code %s" % response.status_code
                print response.content

    def _prepare_event(self, event):
        for attr in ['src', 'dest']:
            if hasattr(event, '%s_path' % attr):
                event_path = getattr(event, '%s_path' % attr)
                event_rel_path = relpath(event_path, self.relpath)
                setattr(event, 'rel_%s_path' % attr, event_rel_path)
                event_base_path = os.path.basename(event_path)
                setattr(event, 'base_%s_path' % attr, event_base_path)
                sync_dir = event_rel_path.startswith(
                    ('templates/', 'static/', 'private/'))
                if not sync_dir:
                    syncable = False
                elif is_hidden(event_base_path):
                    syncable = False
                    name = 'directories' if event.is_directory else 'files'
                    error_msg = 'Hidden %s aren\'t synchronized.' % name
                    setattr(event, 'sync_%s_error' % attr, error_msg)
                elif event.is_directory:
                    syncable = True
                else:
                    try:
                        syncable = is_valid_file_name(event_base_path)
                    except ValidationError as e:
                        syncable = False
                        setattr(event, 'sync_%s_error' % attr, e.message)
                setattr(event, 'sync_%s' % attr, syncable)
        return event

    def dispatch(self, raw_event):
        event_base_name = os.path.basename(raw_event.src_path)
        if event_base_name not in IGNORED_FILES:
            event = self._prepare_event(raw_event)
            super(SyncEventHandler, self).dispatch(event)

    def _set_created_event(self, event_struct):
        filepath = uniform_filepath(event_struct.event.src_path)
        with self._events_lock:
            self._created_events[filepath] = event_struct

    def _set_modified_event(self, event_struct):
        filepath = uniform_filepath(event_struct.event.src_path)
        with self._events_lock:
            self._modified_events[filepath] = event_struct

    def _set_moved_event(self, event_struct):
        filepath = uniform_filepath(event_struct.event.src_path)
        with self._events_lock:
            self._moved_events[filepath] = event_struct

    def _set_deleted_event(self, event_struct):
        filepath = uniform_filepath(event_struct.event.src_path)
        with self._events_lock:
            self._deleted_events[filepath] = event_struct

    def on_moved(self, event):
        if event.is_directory:
            self.on_dir_moved(event)
        else:
            self.on_file_moved(event)

    def on_dir_moved(self, event):
        if event.sync_src:
            if event.sync_dest:
                now = datetime.datetime.now()
                self._set_moved_event(EventStruct(now, event))
            else:
                # moved outside of the syncable area, removing
                sync_logger.debug(
                    'Event "%r" was changed into deleted one' % event)
                raw_delete_event = FileDeletedEvent(event.src_path)
                delete_event = self._prepare_event(raw_delete_event)
                self.on_deleted(delete_event)
        elif event.sync_dest:
            # source isn't in sync area, but dest is, so create the stuff
            sync_logger.debug('Event "%r" was changed into create one' % event)
            raw_create_event = DirCreatedEvent(event.dest_path)
            create_event = self._prepare_event(raw_create_event)
            self.on_created(create_event)

    def on_file_moved(self, event):
        if event.sync_src:
            if event.sync_dest:
                now = datetime.datetime.now()
                self._set_moved_event(EventStruct(now, event))
            else:
                # moved outside of the syncable area, removing
                sync_logger.debug(
                    'Event "%r" was changed into deleted one' % event)
                raw_delete_event = FileDeletedEvent(event.src_path)
                delete_event = self._prepare_event(raw_delete_event)
                self.on_deleted(delete_event)
        elif event.sync_dest:
            # moved inside sync, create
            sync_logger.debug('Event "%r" was changed into create one' % event)
            raw_create_event = FileCreatedEvent(event.dest_path)
            create_event = self._prepare_event(raw_create_event)
            self.on_created(create_event)

    def on_created(self, event):
        if not event.sync_src:
            sync_logger.debug('"on_created" not a syncable file "%s": %s' %
                              (event.src_path, event.sync_src_error))
            print ('Cannot sync file "%s": %s' %
                   (event.rel_src_path, event.sync_src_error))
            return
        if not os.path.exists(event.src_path):
            sync_logger.error(
                'Created file "%s" but it doesn\'t exist.' % event.src_path)
        elif event.is_directory:
            # check if it has content, if so create stuff
            for thing in os.listdir(event.src_path):
                raw_create_event = FileCreatedEvent(
                    os.path.join(event.src_path, thing))
                create_event = self._prepare_event(raw_create_event)
                self.on_created(create_event)
        else:
            now = datetime.datetime.now()
            self._set_created_event(EventStruct(now, event))

    def on_deleted(self, event):
        if not event.sync_src:
            return
        now = datetime.datetime.now()
        self._set_deleted_event(EventStruct(now, event))

    def _file_changed(self, filepath):
        filepath = uniform_filepath(filepath)
        with open(filepath) as fd:
            file_hash = hashfile(fd)
            with self._hashes_lock:
                previous_file_hash = self._recently_modified_file_hashes.get(
                    filepath, None)
                if file_hash != previous_file_hash:
                    self._recently_modified_file_hashes[filepath] = file_hash
                    return True

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.sync_src:
            if self._file_changed(event.src_path):
                now = datetime.datetime.now()
                self._set_modified_event(EventStruct(now, event))
