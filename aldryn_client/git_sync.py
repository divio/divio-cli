# -*- coding: utf-8 -*-
import datetime
import os
import platform
import requests
import shutil
import threading
import time
import traceback

from git.exc import GitCommandError

from .utils import (
    ValidationError, is_hidden, is_valid_file_name, resource_path,
    uniform_filepath)
from .sync_helpers import (
    BACKUP_COUNT, LOG_FILENAME, get_site_specific_logger, git_changes,
    git_pull_develop_bundle, extra_git_kwargs)

SYNCABLE_DIRECTORIES = ('templates/', 'static/', 'private/')

IGNORED_FILES = set(['.aldryn', '.aldryn-folder', '.aldryn-sync-lock',
                     '.DS_Store', LOG_FILENAME])
for i in xrange(1, BACKUP_COUNT + 1):
    IGNORED_FILES.add('%s.%d' % (LOG_FILENAME, i))

CHANGES_CHECK_DELAY = 0.5  # 0.5s
SYNC_BACK_EVERY_X_CHECKS = 10  # 5s
MAX_SYNC_RETRY_COUNT = 2


def update_env_path_with_git_bin():
    system = platform.system()
    if system == 'Darwin':
        os.environ['PATH'] = '%s:' % resource_path('resources/mac_osx/bin') + os.environ['PATH']
        os.environ['GIT_EXEC_PATH'] = resource_path('resources/mac_osx/libexec/git-core')
    elif system == 'Windows':
        os.environ['PATH'] = '%s;' % resource_path('resources/windows/bin') + os.environ['PATH']
    elif system == 'Linux':
        os.environ['PATH'] = '%s:' % resource_path('resources/linux/bin') + os.environ['PATH']
        os.environ['GIT_EXEC_PATH'] = resource_path('resources/linux/libexec/git-core')
        pass
    else:
        pass  # TODO
update_env_path_with_git_bin()


class GitSyncHandler(object):

    def __init__(self, client, sitename, repo, last_synced_commit,
                 network_error_callback, sync_error_callback, stop_sync_callback,
                 protected_files, protected_file_change_callback,
                 relpath='.', sync_indicator_callback=None):
        self.client = client
        self.sitename = sitename
        self.repo = repo
        self._last_synced_commit = last_synced_commit
        self.relpath = uniform_filepath(relpath)
        self.sync_logger = get_site_specific_logger(sitename, self.relpath)
        self._sync_stopped_event = threading.Event()
        # UI callbacks
        self._network_error_callback = network_error_callback
        self._sync_error_callback = sync_error_callback
        self._stop_sync_callback = stop_sync_callback
        self._sync_indicator_callback = sync_indicator_callback
        # protected files
        self._protected_files = protected_files
        self._overridden_protected_files = set()
        self._protected_file_change_callback = protected_file_change_callback
        # warnings about incorret files
        self._already_notified_incorrect_files = set()
        # sync error dialog handlers
        self._sync_error_dialogs = []

    def start(self):
        self._send_changes_thread = threading.Thread(
            target=self._send_changes_worker, name='Changes sender')
        self._send_changes_thread.start()

    def stop(self):
        try:
            self.client.session.post('/api/v1/sync/%s/sync-log-stop/' % self.sitename)
        except Exception as e:
            # suppress exception, this request isn't that important, sync will
            # eventually be marked as stopped
            print e
        self._sync_stopped_event.set()
        if hasattr(self, '_send_changes_thread'):
            self._send_changes_thread.join()
        self.client._remove_sync_lock(self.relpath)
        if self.sitename in self.client._sync_handlers_cache:
            del self.client._sync_handlers_cache[self.sitename]

    def _send_changes_worker(self):
        iteration_counter = 0
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
                if (file_rel_path in self._protected_files and
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
                elif filepath not in self._already_notified_incorrect_files:
                    self._already_notified_incorrect_files.add(filepath)
                    msg = 'not a syncable file: "%s": %s' % (filepath, error_msg)
                    self._sync_error_callback(msg)
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
                for key, values in changes.items():
                    if values:
                        print ('%s:' % key),
                        for value in values:
                            print ('\t%s' % value),
                        print
                self._commit_changes()

            stop_timestamp = datetime.datetime.now()
            time_elapsed_delta = stop_timestamp - start_timestamp
            delay = CHANGES_CHECK_DELAY - time_elapsed_delta.total_seconds()
            if delay > 0:
                time.sleep(delay)
            iteration_counter += 1
            if iteration_counter % SYNC_BACK_EVERY_X_CHECKS == 0:
                self._sync_back_upstream_changes()

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

        if self._sync_indicator_callback:
            self._sync_indicator_callback()
        try_count = 0
        while not exit_loop_event.isSet():
            try_count += 1
            sync_bundle_path = os.path.join(self.relpath, '.sync.bundle')
            commits_range = '%s..develop' % self._last_synced_commit
            self.repo.git.execute(
                ['git', 'bundle', 'create', sync_bundle_path, commits_range],
                **extra_git_kwargs)
            try:
                with open(sync_bundle_path, 'rb') as fobj:
                    response = self._send_request(files={'content': fobj})
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                retry_event.clear()
                from .client import Client
                message = Client.SYNC_NETWORK_ERROR_MESSAGE
                self._network_error_callback(
                    message, on_confirm, on_cancel)
                retry_event.wait()
            else:
                if response.ok:
                    # Dismiss previous sync error dialogs
                    for dialog in self._sync_error_dialogs:
                        if dialog and hasattr(dialog, 'dismiss'):
                            dialog.dismiss()
                    self._sync_error_dialogs = []
                    # Updating local "file" remote after successful sync of the commits
                    develop_bundle_path = os.path.join(self.relpath, '.develop.bundle')
                    shutil.move(sync_bundle_path, develop_bundle_path)
                    self.repo.git.execute(
                        ['git', 'fetch', 'develop_bundle'], **extra_git_kwargs)

                    self._last_synced_commit = self.repo.git.execute(
                        ['git', 'rev-parse', 'develop_bundle/develop'], **extra_git_kwargs)
                    exit_loop_event.set()
                elif response.status_code == 409 and try_count <= MAX_SYNC_RETRY_COUNT:
                    # probably upstream has some new commits which we need to pull
                    self.sync_logger.debug(response.content)
                    self._sync_back_upstream_changes()
                elif response.status_code == 403:
                    msg = response.content
                    self._stop_sync_callback(msg, force=True, logout=True)
                    exit_loop_event.set()
                else:
                    title = "Sync failed!"
                    if response.status_code in (400, 409):
                        msg = response.content
                    else:
                        base_msg = "Unexpected status code %s" % response.status_code
                        if response.status_code < 500:
                            msg = '\n'.join([base_msg, response.content])
                        else:
                            msg = '\n'.join([base_msg, "Internal Server Error"])
                    sync_error_dialog = self._sync_error_callback(msg, title=title)
                    self._sync_error_dialogs.append(sync_error_dialog)
                    exit_loop_event.set()
            # endwhile
        if self._sync_indicator_callback:
            self._sync_indicator_callback(stop=True)

    def _sync_back_upstream_changes(self):
        try:
            last_synced_commit = self.repo.git.execute(
                ['git', 'rev-parse', 'develop_bundle/develop'],
                **extra_git_kwargs)
            git_sync_params = {'last_synced_commit': last_synced_commit}
            response = self.client.session.get(
                '/api/v1/git-sync/%s/' % self.sitename, params=git_sync_params,
                stream=True, headers={'accept': 'application/octet'})
            if response.status_code == 304:
                pass  # NOT MODIFIED
            elif response.status_code == 200:
                git_pull_develop_bundle(response, self.repo, self.relpath)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout, GitCommandError):
            stack_trace = traceback.format_exc()
            print 'Suppressing pull update error:\n%s' % stack_trace

    def _send_request(self, *args, **kwargs):
        headers = kwargs.get('headers', {})
        if 'accept' not in headers:
            headers['accept'] = 'text/plain'
        kwargs['headers'] = headers
        response = self.client.session.request(
            'POST', '/api/v1/git-sync/%s/' % self.sitename, *args, **kwargs)
        return response
