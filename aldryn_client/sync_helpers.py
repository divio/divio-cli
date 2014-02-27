# -*- coding: utf-8 -*-
import logging
import logging.handlers
import os

###############################################################################
# Logging configuration
###############################################################################
BACKUP_COUNT = 2
FORMAT = '%(asctime)s|%(name)s|%(levelname)s: %(message)s'
LOG_FILENAME = '.sync.log'
MAX_BYTES = 100 * (2 ** 10)  # 100KB
SYNCABLE_DIRECTORIES = ('templates/', 'static/', 'private/')


extra_git_kwargs = {}
if os.name == 'nt':
        import subprocess
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        extra_git_kwargs['startupinfo'] = startupinfo
        istream = subprocess.PIPE
        extra_git_kwargs['istream'] = istream


def get_site_specific_logger(sitename, site_dir):
    log_filename = os.path.join(site_dir, LOG_FILENAME)
    rotating_handler = logging.handlers.RotatingFileHandler(
        log_filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    formatter = logging.Formatter(FORMAT)
    rotating_handler.setFormatter(formatter)
    rotating_handler.setLevel(logging.DEBUG)

    sync_logger = logging.getLogger(sitename)
    sync_logger.setLevel(logging.DEBUG)
    sync_logger.handlers = []
    sync_logger.addHandler(rotating_handler)
    return sync_logger
###############################################################################


def git_changes(repo):
    added = []
    deleted = []
    other = []
    git_status = repo.git.execute(
        ['git', 'status', '--porcelain', '--untracked-files=all'],
        **extra_git_kwargs)
    if git_status:
        for change in git_status.split('\n'):
            # change[0] contains staged status
            unstaged_status = change[1]
            path = change[3:]
            if unstaged_status in ['M', '?']:
                added.append(path)
            elif unstaged_status == 'D':
                deleted.append(path)
            else:
                other.append(path)
    return {'added': added, 'deleted': deleted, 'other': other}


def git_update_gitignore(repo, new_ignore_patterns):
    gitignore_filepath = os.path.join(repo.working_dir, '.gitignore')
    ignored_set = set()
    with open(gitignore_filepath, 'r') as fobj:
        for line in fobj.readlines():
            ignored_set.add(line.strip())
    need_updating = False
    for new_ignore in new_ignore_patterns:
        new_ignore = new_ignore.strip()
        if new_ignore not in ignored_set:
            need_updating = True
            ignored_set.add(new_ignore)
    if need_updating:
        with open(gitignore_filepath, 'w') as fobj:
            new_gitignore_str = '\n'.join(sorted(ignored_set))
            fobj.write(new_gitignore_str)
        repo.git.execute(['git', 'add', gitignore_filepath], **extra_git_kwargs)
        repo.git.execute(['git', 'commit', '-m Update gitignore'], **extra_git_kwargs)


def git_pull_develop_bundle(response, repo, path):
    bundle_path = os.path.join(path, '.develop.bundle')
    with open(bundle_path, 'wb') as fobj:
        for chunk in response.iter_content(512 * 1024):
            if not chunk:
                break
            fobj.write(chunk)
    if not 'develop_bundle' in repo.git.execute(
            ['git', 'remote'], **extra_git_kwargs).split():
        repo.git.execute(
            ['git', 'remote', 'add', 'develop_bundle', bundle_path],
            **extra_git_kwargs)
    repo.git.execute(
        ['git', 'fetch', 'develop_bundle'], **extra_git_kwargs)
    if not 'develop' in repo.git.execute(
            ['git', 'branch'], **extra_git_kwargs).split():
        repo.git.execute(
            ['git', 'checkout', '-bdevelop', 'develop_bundle/develop'],
            **extra_git_kwargs)
    repo.git.execute(['git', 'merge', 'develop_bundle/develop', 'develop'],
                     **extra_git_kwargs)
