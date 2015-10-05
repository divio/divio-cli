import json
import tarfile
import re
import os
import subprocess
from StringIO import StringIO
from time import sleep

import click
import requests

from ..utils import dev_null, execute, redirect_stdout
from ..cloud import get_aldryn_host
from .. import settings
from . import utils


DEFAULT_GIT_HOST = 'git@git.{aldryn_host}'
GIT_CLONE_URL = '{git_host}:{project_slug}.git'


def get_git_host():
    git_host = os.environ.get('ALDRYN_GIT_HOST')
    if git_host:
        click.secho('Using custom git host {}\n'.format(git_host), fg='yellow')
    else:
        git_host = DEFAULT_GIT_HOST.format(aldryn_host=get_aldryn_host())
    return git_host


def get_git_clone_url(slug):
    return GIT_CLONE_URL.format(git_host=get_git_host(), project_slug=slug)


def create_workspace(client, website_slug, path=None):
    click.secho('Creating workspace...', fg='green')

    path = os.path.abspath(
        os.path.join(path, website_slug)
        if path else website_slug
    )

    docker_compose = utils.get_docker_compose_cmd(path)
    website_id = client.get_website_id_for_slug(website_slug)
    website_git_url = get_git_clone_url(website_slug)

    try:
        click.secho('\ncloning project repository', fg='green')
        clone_args = ['git', 'clone', website_git_url]
        if path:
            clone_args.append(path)
        execute(clone_args, silent=False, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(exc.output)

    # Detect old style or invalid projects
    compose_config = os.path.join(path or website_slug, 'docker-compose.yml')
    if not os.path.isfile(compose_config):
        raise click.ClickException(
            "Aldryn local development only works with projects using "
            "baseproject version 3 and have a valid 'docker-compose.yml' file."
        )

    # create .aldryn file
    website_data = {'id': website_id, 'slug': website_slug}
    with open(os.path.join(path, settings.ALDRYN_DOT_FILE), 'w+') as fh:
        json.dump(website_data, fh)

    existing_db_container_id = utils.get_db_container_id(path)

    # stop all running for project
    execute(docker_compose('stop'), silent=True)

    # pull docker images
    click.secho('downloading remote docker images', fg='green')
    execute(docker_compose('pull'), silent=False, stderr=subprocess.STDOUT)

    # build docker images
    click.secho('building local docker images', fg='green')
    execute(docker_compose('build'), silent=False, stderr=subprocess.STDOUT)

    if existing_db_container_id:
        click.secho('removing old database container', fg='green')
        execute(
            docker_compose('stop', 'db'),
            stderr=subprocess.STDOUT,
            silent=False,
        )
        execute(
            docker_compose('rm', '-f', 'db'),
            stderr=subprocess.STDOUT,
            silent=False,
        )

    click.secho('creating new database container', fg='green')
    load_database_dump(client, path, recreate=True)

    click.secho('sync and migrate database', fg='green')
    # FIXME: Running this command with silent=False raises:
    #   IOError: [Errno 35] Resource temporarily unavailable
    #   see http://trac.edgewall.org/ticket/2066
    execute(
        docker_compose('run', 'web', './migrate.sh'),
        stderr=subprocess.STDOUT,
        silent=True,  # silent=False raises
    )

    instructions = [
        "Finished setting up your project's workspace!",
        "To start the project, please:",
    ]

    if path:
        instructions.append(' - change directory into {}'.format(path))
    instructions.append(' - run aldryn project up')

    click.secho('\n\n{}'.format(os.linesep.join(instructions)), fg='green')


def load_database_dump(client, path=None, recreate=False):
    path = path or utils.get_project_home(path)
    website_slug = utils.get_aldryn_project_settings(path)['slug']
    docker_compose = utils.get_docker_compose_cmd(path)

    start_db_cmd = ['up', '-d']
    if recreate:
        start_db_cmd.append('--force-recreate')
    start_db_cmd.append('db')

    # start db
    execute(
        docker_compose(*start_db_cmd),
        stderr=subprocess.STDOUT,
        silent=True,
    )

    # get db container id
    db_container_id = utils.get_db_container_id(path)

    click.secho('fetching database dump', fg='green')
    db_dump_path = client.download_db(website_slug, directory=path)
    # strip path from dump_path for use in the docker container
    db_dump_path = db_dump_path.replace(path, '')

    # waiting another 10 seconds to make sure
    # the db has enough time to start
    sleep(10)

    # create empty db
    try:
        execute([
            'docker', 'exec', db_container_id,
            'dropdb', '-U', 'postgres', 'db',
        ], silent=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        pass

    execute([
        'docker', 'exec', db_container_id,
        'createdb', '-U', 'postgres', 'db',
    ], silent=True, stderr=subprocess.STDOUT)

    click.secho('inserting database dump', fg='green')
    # FIXME: because of different ownership,
    # this spits a lot of warnings which can
    # ignored but we can't really validate success
    with dev_null() as devnull:
        try:
            piped_restore = (
                'tar -xzOf /app/{}'
                ' | pg_restore -U postgres -d db'
                .format(db_dump_path)
            )
            subprocess.call((
                'docker', 'exec', db_container_id,
                '/bin/bash', '-c', piped_restore,
            ), stdout=devnull, stderr=devnull)
        except subprocess.CalledProcessError:
            pass

    # stop db
    execute(
        docker_compose('stop'),
        silent=True,
        stderr=subprocess.STDOUT,
    )


def download_media(client, path=None):
    click.secho('fetching media files', fg='green')

    path = path or os.path.join(utils.get_project_home(path), 'data/media')
    website_slug = utils.get_aldryn_project_settings(path)['slug']
    backup_path = client.download_backup(website_slug)

    with tarfile.open(backup_path, 'r:gz') as backup_archive:
        media_archive_name = 'media_files.tar.gz'
        if media_archive_name not in backup_archive.getnames():
            click.secho('Media archive empty', fg='yellow')
            return

        media_fobj = backup_archive.extractfile(media_archive_name)
        with tarfile.open(fileobj=media_fobj, mode='r:gz') as media_archive:
            media_archive.extractall(path=path)

    os.remove(backup_path)
    click.secho('Downloaded media files into {}'.format(path), fg='green')


def upload_database(client):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)['id']
    dump_filename = 'local_db.sql'
    archive_filename = 'local_db.tar.gz'
    archive_path = os.path.join(project_home, archive_filename)
    docker_compose = utils.get_docker_compose_cmd(project_home)

    # start db
    execute(
        docker_compose('up', '-d', 'db'),
        stderr=subprocess.STDOUT,
        silent=True,
    )

    # take dump of database
    click.secho('Dumping local database', fg='green')
    db_container_id = utils.get_db_container_id(project_home)

    subprocess.call((
        'docker', 'exec', db_container_id,
        'pg_dump', '-U', 'postgres', '-d', 'db',
        '-f', os.path.join('/app/', dump_filename)
    ))

    click.secho('Creating archive of SQL dump', fg='green')
    with tarfile.open(archive_path, mode='w:gz') as tar:
        tar.add(
            os.path.join(project_home, dump_filename),
            arcname=dump_filename
        )

    click.secho('Pushing database to Aldryn', fg='green')
    client.upload_db(website_id, archive_path)
    # clean up
    for temp_file in (dump_filename, archive_filename):
        os.remove(os.path.join(project_home, temp_file))
    click.secho('Done', fg='green')


def upload_media(client):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)['id']
    archive_path = os.path.join(project_home, 'local_media.tar.gz')

    click.secho('Creating archive of local media folder', fg='green')
    with tarfile.open(archive_path, mode='w:gz') as tar:
        media_dir = os.path.join(project_home, 'data', 'media')
        for item in os.listdir(media_dir):
            tar.add(os.path.join(media_dir, item), arcname=item)

    click.secho('Pushing archive to Aldryn', fg='green')
    client.upload_media_files(website_id, archive_path)

    # clean up
    os.remove(archive_path)
    click.secho('Done', fg='green')


def develop_package(package, no_rebuild=False):
    """
    :param package: package name in addons-dev folder
    """

    project_home = utils.get_project_home()
    addons_dev_dir = os.path.join(project_home, 'addons-dev')

    if not os.path.isdir(os.path.join(addons_dev_dir, package)):
        raise click.ClickException(
            'Package {} could not be found in {}. Please make '
            'sure it exists and try again.'
            .format(package, addons_dev_dir)
        )

    url_pattern = re.compile('(\S*/{}/\S*)'.format(package))
    new_package_path = '-e /app/addons-dev/{}\n'.format(package)

    # add package to requirements.in for dependencies
    requirements_file = os.path.join(project_home, 'requirements.in')
    # open file with 'universal newline support'
    # https://docs.python.org/2/library/functions.html#open
    with open(requirements_file, 'rU') as fh:
        addons = fh.readlines()

    replaced = False

    for counter, addon in enumerate(addons):
        if re.match(url_pattern, addon) or addon == new_package_path:
            addons[counter] = new_package_path
            replaced = True
            break

    if not replaced:
        # Not replaced, append to generated part of requirements
        for counter, addon in enumerate(addons):
            if '</INSTALLED_ADDONS>' in addon:
                addons.insert(counter, new_package_path)
                replaced = True
                break

    if not replaced:
        # fallback: generated section seems to be missing, appending
        addons.append(new_package_path)

    with open(requirements_file, 'w') as fh:
        fh.writelines(addons)

    if not no_rebuild:
        # build web again
        docker_compose = utils.get_docker_compose_cmd(project_home)

        try:
            execute(
                docker_compose('build', 'web'),
                silent=False,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as exc:
            raise click.ClickException(exc.output)

    click.secho(
        'The package {} has been added to your local development project!'
        .format(package)
    )


def open_project(open_browser=True):
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    try:
        addr = execute(docker_compose('port', 'web', '80'), silent=True)
    except subprocess.CalledProcessError:
        if click.prompt('Your project is not running. Do you want to start '
                        'it now?'):
            return start_project()
        return
    host, port = addr.split(':')

    if host == '0.0.0.0':
        docker_host_url = os.environ.get('DOCKER_HOST')
        if docker_host_url:
            proto, host_port = os.environ.get('DOCKER_HOST').split('://')
            host = host_port.split(':')[0]

    addr = 'http://{host}:{port}/'.format(
        host=host.replace(os.linesep, ''),
        port=port.replace(os.linesep, ''),
    )

    click.secho(
        'Your project is configured to run at {}'.format(addr),
        fg='green'
    )

    click.secho('Waiting for project to start..', fg='green', nl=False)
    # wait 30s for runserver to startup
    seconds = 30
    for attempt in range(seconds):
        click.secho('.', fg='green', nl=False)
        try:
            requests.head(addr)
        except requests.ConnectionError:
            sleep(1)
        else:
            break

        if attempt == seconds - 1:
            raise click.ClickException(
                "\nProject failed to start. Please run 'docker-compose logs' "
                "to get more information."
            )

    if open_browser:
        click.launch(addr)
    return addr


def start_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    my_stdout = StringIO()
    try:
        with redirect_stdout(my_stdout):
            execute(docker_compose('up', '-d'), stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        my_stdout.seek(0)
        output = my_stdout.read()
        if 'port is already allocated' in output:
            click.secho(
                "There's already another program running on this project's "
                "port. Please either stop the other program or change the"
                "port in the 'docker-compose.yml' file and try again.\n",
                fg='red'
            )
        raise click.ClickException(output)

    return open_project(open_browser=True)


def stop_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    execute(docker_compose('stop'))
