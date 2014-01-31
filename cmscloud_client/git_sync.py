# -*- coding: utf-8 -*-
import datetime
import os
import platform
import requests
import shutil
import threading
import time

from git.exc import GitCommandError

from .utils import (
    ValidationError, is_hidden, is_valid_file_name, resource_path,
    uniform_filepath)
from .sync_helpers import (
    BACKUP_COUNT, LOG_FILENAME, get_site_specific_logger, git_changes,
    extra_git_kwargs)

SYNCABLE_DIRECTORIES = ('templates/', 'static/', 'private/')

IGNORED_FILES = set(['.cmscloud', '.cmscloud-folder', '.cmscloud-sync-lock',
                     '.DS_Store', LOG_FILENAME])
for i in xrange(1, BACKUP_COUNT + 1):
    IGNORED_FILES.add('%s.%d' % (LOG_FILENAME, i))

CHANGES_CHECK_DELAY = 1.0


def update_env_path_with_git_bin():
    system = platform.system()
    if system == 'Darwin':
        os.environ['PATH'] = '%s:' % resource_path('resources/mac_osx/bin') + os.environ['PATH']
        os.environ['GIT_EXEC_PATH'] = resource_path('resources/mac_osx/libexec/git-core')
    elif system == 'Windows':
        os.environ['PATH'] = '%s;' % resource_path('resources/windows/bin') + os.environ['PATH']
    else:
        pass  # TODO
update_env_path_with_git_bin()


class GitSyncHandler(object):

    def __init__(self, client, sitename, repo, last_synced_commit,
                 network_error_callback, sync_error_callback,
                 protected_files, protected_file_change_callback,
                 relpath='.', sync_indicator_callback=None):
        self.client = client
        self.sitename = sitename
        self.repo = repo
        self._last_synced_commit = last_synced_commit
        self.relpath = uniform_filepath(relpath)
        self.sync_logger = get_site_specific_logger(sitename, self.relpath)
        self._sync_stopped_event = threading.Event()
        self._network_error_callback = network_error_callback
        self._sync_error_callback = sync_error_callback
        self._sync_indicator_callback = sync_indicator_callback
        self._protected_files = protected_files
        self._overridden_protected_files = set()
        self._protected_file_change_callback = protected_file_change_callback

    def start(self):
        self._send_changes_thread = threading.Thread(
            target=self._send_changes_worker, name='Changes sender')
        self._send_changes_thread.start()

    def stop(self):
        self._sync_stopped_event.set()
        if hasattr(self, '_send_changes_thread'):
            self._send_changes_thread.join()
        self.client._remove_sync_lock(self.relpath)
        if self.sitename in self.client._sync_handlers_cache:
            del self.client._sync_handlers_cache[self.sitename]

    def _send_changes_worker(self):
        while not self._sync_stopped_event.isSet():
            start_timestamp = datetime.datetime.now()
            changes = git_changes(self.repo)
            commit = False
            added_files = changes['added']
            for file_rel_path in added_files:
                filepath = os.path.join(self.relpath, file_rel_path)
                file_basename = os.path.basename(filepath)
                if file_basename in IGNORED_FILES:
                    continue
                if (file_basename in self._protected_files and
                        file_rel_path not in self._overridden_protected_files):
                    from .client import Client
                    message = Client.PROTECTED_FILE_CHANGE_MESSAGE % filepath
                    self._protected_file_change_callback(message)
                    self._overridden_protected_files.add(file_rel_path)

                syncable = True
                in_sync_dir = file_rel_path.startswith(SYNCABLE_DIRECTORIES)
                if not in_sync_dir:
                    error_msg = ('Not in the syncable directory: %s' %
                                 (', '.join(SYNCABLE_DIRECTORIES)))
                    syncable = False
                elif is_hidden(file_basename):
                    error_msg = 'Hidden files aren\'t synchronized.'
                    syncable = False
                else:
                    def raiser(msg):
                        raise ValidationError(msg)

                    try:
                        syncable = is_valid_file_name(
                            file_basename, logger=raiser)
                    except ValidationError as e:
                        syncable = False
                        error_msg = e.message
                if syncable:
                    commit = True
                    self.repo.git.execute(
                        ['git', 'add', file_rel_path], **extra_git_kwargs)
                else:
                    msg = 'not a syncable file: "%s": %s' % (filepath, error_msg)
                    self.sync_logger.info(msg)
            deleted_files = changes['deleted']
            for file_rel_path in deleted_files:
                filepath = os.path.join(self.relpath, file_rel_path)
                if not os.path.exists(filepath):
                    try:
                        self.repo.git.execute(
                            ['git', 'rm', file_rel_path], **extra_git_kwargs)
                    except GitCommandError:
                        # Some editors remove the original file and rename
                        # the updated copy. We just run the command during the
                        # process.
                        pass
                    else:
                        commit = True
            if commit:
                print changes
                self._commit_changes()

            stop_timestamp = datetime.datetime.now()
            time_elapsed_delta = stop_timestamp - start_timestamp
            delay = CHANGES_CHECK_DELAY - time_elapsed_delta.total_seconds()
            if delay > 0:
                time.sleep(delay)

    def _commit_changes(self):
        self.sync_logger.debug('Sending changes:\t' + self.repo.git.execute(
            ['git', 'status', '--porcelain'], **extra_git_kwargs))
        try:
            self.repo.git.execute(
                ['git', 'commit', '-m Git Sync'], **extra_git_kwargs)
        except Exception as e:
            print e
            # TODO this sometimes fails, probably due to file being modified again
            # while committing, we just skip this sync turn and try next time
            return

        retry_event = threading.Event()
        exit_loop_event = threading.Event()

        def on_confirm():
            retry_event.set()

        def on_cancel():
            exit_loop_event.set()
            retry_event.set()

        sync_bundle_path = os.path.join(self.relpath, '.sync.bundle')
        commits_range = '%s..develop' % self._last_synced_commit
        self.repo.git.execute(
            ['git', 'bundle', 'create', sync_bundle_path, commits_range],
            **extra_git_kwargs)
        fobj = open(sync_bundle_path, 'rb')
        kwargs = {'files': {'content': fobj}}

        if self._sync_indicator_callback:
            self._sync_indicator_callback()
        success = False
        while not exit_loop_event.isSet():
            if fobj:  # reseting the read state of the sending file
                fobj.seek(0)
            try:
                success = self._send_request(**kwargs)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                retry_event.clear()
                from .client import Client
                message = Client.SYNC_NETWORK_ERROR_MESSAGE
                self._network_error_callback(
                    message, on_confirm, on_cancel)
                retry_event.wait()
            else:
                fobj.close()
                exit_loop_event.set()
        if success:
            # Updating local "file" remote after successful sync of the commits
            develop_bundle_path = os.path.join(self.relpath, '.develop.bundle')
            shutil.move(sync_bundle_path, develop_bundle_path)
            self.repo.git.execute(
                ['git', 'fetch', 'develop_bundle'], **extra_git_kwargs)

            self._last_synced_commit = self.repo.git.execute(
                ['git', 'rev-parse', 'develop'], **extra_git_kwargs)
        if self._sync_indicator_callback:
            self._sync_indicator_callback(stop=True)

    def _send_request(self, *args, **kwargs):
        headers = kwargs.get('headers', {})
        if 'accept' not in headers:
            headers['accept'] = 'text/plain'
        kwargs['headers'] = headers
        response = self.client.session.request(
            'POST', '/api/v1/git-sync/%s/' % self.sitename, *args, **kwargs)
        if response.ok:
            return True
        else:
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
            return False
