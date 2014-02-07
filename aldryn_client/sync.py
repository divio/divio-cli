# -*- coding: utf-8 -*-
import datetime
import os
import requests
import threading
import time

from watchdog.events import (
    DirCreatedEvent, DirDeletedEvent, FileCreatedEvent, FileDeletedEvent,
    FileSystemEventHandler)

from .utils import uniform_filepath
from .sync_helpers import (
    EventsBuffer, FileHashesCache, ProceededEventsQueue, SyncEvent,
    get_site_specific_logger, BACKUP_COUNT, LOG_FILENAME)

# Amount of time during which we collect events and perform heuristics
# to reduce the number of requests
TIME_DELTA_IN_SECONDS = 0.5

# Waiting twice (and a bit) as long as it takes to consider subsequent events
# as a single action e.g. directory move, file save (by 'moving/renaming'),
# to collect all actions from a single "batch" into (preferably) single request
COLLECT_TIME_DELTA_IN_SECONDS = TIME_DELTA_IN_SECONDS * 2.01

IGNORED_FILES = set(['.aldryn', '.aldryn-folder', '.aldryn-sync-lock',
                     '.DS_Store', LOG_FILENAME])
for i in xrange(1, BACKUP_COUNT + 1):
    IGNORED_FILES.add('%s.%d' % (LOG_FILENAME, i))

###############################################################################
# End of constants
###############################################################################


class SyncEventHandler(FileSystemEventHandler):

    def __init__(self, session, sitename, observer_stopped,
                 network_error_callback, sync_error_callback,
                 protected_files, protected_file_change_callback,
                 relpath='.', sync_indicator_callback=None):
        self.session = session
        self.sitename = sitename
        self.relpath = uniform_filepath(relpath)
        self.sync_logger = get_site_specific_logger(sitename, self.relpath)
        self._observer_stopped = observer_stopped
        self._network_error_callback = network_error_callback
        self._sync_error_callback = sync_error_callback
        self._sync_indicator_callback = sync_indicator_callback
        self._protected_files = protected_files
        self._overridden_protected_filed = set()
        self._protected_file_change_callback = protected_file_change_callback

        self._recently_modified_file_hashes = {}

        self._events_buffer = EventsBuffer(self.relpath)

        self._proceeded_events_queue = ProceededEventsQueue()

        self._file_hashes_cache = FileHashesCache(self.relpath)
        self._file_hashes_cache.update_hashes()

        # Due to the asynchronous nature of the file system's events
        # there should be only one 'sending requests worker'.
        # (e.g. lagging 'create request' followed by a 'delete' one
        # will fail because the fail wasn't created yet)
        self._send_requests_thread = threading.Thread(
            target=self._send_requests_worker, name='Requests sender')
        self._send_requests_thread.start()

        self._collect_events_thread = threading.Thread(
            target=self._collect_events_worker, name='Events collector')
        self._collect_events_thread.start()

    def _collect_events_worker(self):
        while not self._observer_stopped.isSet():
            start_timestamp = datetime.datetime.now()

            oldest_events_buffer = (
                self._events_buffer.filter_out_oldest_events_buffer(
                    TIME_DELTA_IN_SECONDS))
            oldest_events_buffer.log_state(self.sync_logger)
            reduced_sync_events = oldest_events_buffer.get_reduced_events_list(
                self._file_hashes_cache.is_file_changed,
                self.sync_logger)
            for sync_event in reduced_sync_events:
                self.sync_logger.debug(
                    'Queueing the event:\t' + repr(sync_event))
                self._proceeded_events_queue.put_event(sync_event)

            stop_timestamp = datetime.datetime.now()
            time_elapsed_delta = stop_timestamp - start_timestamp
            delay = COLLECT_TIME_DELTA_IN_SECONDS - time_elapsed_delta.total_seconds()
            if delay > 0:
                time.sleep(delay)

    def _send_requests_worker(self):
        while not self._observer_stopped.isSet():
            sync_event = self._proceeded_events_queue.get_event(
                timeout=TIME_DELTA_IN_SECONDS)
            if sync_event:
                from .client import Client
                rel_src_path = sync_event.rel_src_path
                if (rel_src_path in self._protected_files and
                        rel_src_path not in self._overridden_protected_filed):
                    message = Client.PROTECTED_FILE_CHANGE_MESSAGE % sync_event.src_path
                    self._protected_file_change_callback(message)
                    self._overridden_protected_filed.add(rel_src_path)

                self.sync_logger.debug(
                    'Sending request for event:\t' + repr(sync_event))
                msg, method, kwargs, fobj = sync_event.prepare_request()
                print msg

                retry_event = threading.Event()
                exit_loop_event = threading.Event()

                def on_confirm():
                    retry_event.set()

                def on_cancel():
                    exit_loop_event.set()
                    retry_event.set()

                if self._sync_indicator_callback:
                    self._sync_indicator_callback()
                while not exit_loop_event.isSet():
                    if fobj:  # reseting the read state of the sending file
                        fobj.seek(0)
                    try:
                        self._send_request(method, **kwargs)
                    except (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout):
                        retry_event.clear()
                        message = Client.SYNC_NETWORK_ERROR_MESSAGE % sync_event.src_path
                        self._network_error_callback(
                            message, on_confirm, on_cancel)
                        retry_event.wait()
                    else:
                        if fobj:
                            fobj.close()
                        exit_loop_event.set()
                if self._sync_indicator_callback:
                    self._sync_indicator_callback(stop=True)

    def _send_request(self, method, *args, **kwargs):
        headers = kwargs.get('headers', {})
        if 'accept' not in headers:
            headers['accept'] = 'text/plain'
        kwargs['headers'] = headers
        response = self.session.request(
            method, '/api/v1/sync/%s/' % self.sitename, *args, **kwargs)
        if not response.ok:
            title = "Sync failed!"
            if response.status_code == 400:
                msg = response.content
            else:
                base_msg = "Unexpected status code %s" % response.status_code
                if response.status_code < 500:
                    msg = '\n'.join([base_msg, response.content])
                else:
                    msg = '\n'.join([base_msg, "Internal Server Error"])
            self._sync_error_callback(msg, title=title)

    def dispatch(self, raw_event):
        now = datetime.datetime.now()
        sync_event = SyncEvent(raw_event, now, self.relpath)
        if sync_event.base_src_path not in IGNORED_FILES:
            super(SyncEventHandler, self).dispatch(sync_event)

    def on_moved(self, sync_event):
        if sync_event.is_src_path_syncable:
            if sync_event.is_dest_path_syncable:
                self._events_buffer.set_moved_event(sync_event)
            else:
                self.sync_logger.debug(
                    'Moved outside of the syncable area, removing: %r' % sync_event)
                if sync_event.is_directory:
                    raw_delete_event = DirDeletedEvent(sync_event.src_path)
                else:
                    raw_delete_event = FileDeletedEvent(sync_event.src_path)
                delete_event = SyncEvent(
                    raw_delete_event, sync_event.timestamp, sync_event.relpath)
                self.on_deleted(delete_event)
        elif sync_event.is_dest_path_syncable:
            self.sync_logger.debug(
                'Moved into the syncable area, creating: %r' % sync_event)
            if sync_event.is_directory:
                raw_create_event = DirCreatedEvent(sync_event.dest_path)
            else:
                raw_create_event = FileCreatedEvent(sync_event.dest_path)
            create_event = SyncEvent(
                raw_create_event, sync_event.timestamp, sync_event.relpath)
            self.on_created(create_event)

    def _log_not_a_syncable_file(self, sync_event):
        self.sync_logger.debug(
            'not a syncable file: "%s": %s' %
            (sync_event, sync_event.not_syncable_src_path_reason))
        print ('Cannot sync file "%s": %s' %
               (sync_event.src_path,
                sync_event.not_syncable_src_path_reason))

    def on_created(self, sync_event):
        if not sync_event.is_src_path_syncable:
            self._log_not_a_syncable_file(sync_event)
            return
        if sync_event.is_directory:
            # check if the directory has a content, if so create the stuff
            try:
                for thing in os.listdir(sync_event.src_path):
                    raw_create_event = FileCreatedEvent(
                        os.path.join(sync_event.src_path, thing))
                    create_event = SyncEvent(
                        raw_create_event, sync_event.timestamp, sync_event.relpath)
                    if create_event.base_src_path not in IGNORED_FILES:
                        self.on_created(create_event)
            except os.OSError as e:
                self.sync_logger.error(
                    'Accessing created directory "%s" raised: %r.' %
                    (sync_event.src_path, e))
        else:
            self._events_buffer.set_created_event(sync_event)

    def on_deleted(self, sync_event):
        if not sync_event.is_src_path_syncable:
            self._log_not_a_syncable_file(sync_event)
            return
        self._events_buffer.set_deleted_event(sync_event)

    def on_modified(self, sync_event):
        if sync_event.is_directory:
            # This doesn't mean that the directory was renamed
            # it just means that the content of it was modified
            # which we handle in their own events
            return
        if not sync_event.is_src_path_syncable:
            self._log_not_a_syncable_file(sync_event)
            return
        else:
            self._events_buffer.set_modified_event(sync_event)
