import json
import tarfile
import re
import os
import subprocess
import sys
from time import sleep, time

import click
import requests
import shutil

from ..utils import check_call, check_output, is_windows, pretty_size, get_size
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


def clone_project(website_slug, path):
    click.secho('\ncloning project repository', fg='green')
    website_git_url = get_git_clone_url(website_slug)
    clone_args = ['git', 'clone', website_git_url]
    if path:
        clone_args.append(path)

    check_call(clone_args)


def configure_project(website_slug, path, client):
    website_id = client.get_website_id_for_slug(website_slug)

    # Detect old style or invalid projects
    compose_config = os.path.join(path, 'docker-compose.yml')
    if not os.path.isfile(compose_config):
        raise click.ClickException(
            "Valid 'docker-compose.yml' file not found. Please make sure that "
            "this project has been updated on Aldryn to use Base Project "
            "version 3."
        )

    # create .aldryn file
    website_data = {'id': website_id, 'slug': website_slug}
    with open(os.path.join(path, settings.ALDRYN_DOT_FILE), 'w+') as fh:
        json.dump(website_data, fh)


def setup_website_containers(client, path):
    docker_compose = utils.get_docker_compose_cmd(path)

    existing_db_container_id = utils.get_db_container_id(path)

    # stop all running for project
    check_call(docker_compose('stop'))

    # pull docker images
    click.secho('downloading remote docker images', fg='green')
    check_call(docker_compose('pull'))

    # build docker images
    click.secho('building local docker images', fg='green')
    check_call(docker_compose('build'))

    if existing_db_container_id:
        click.secho('removing old database container', fg='green')
        check_call(docker_compose('stop', 'db'))
        check_call(docker_compose('rm', '-f', 'db'))

    click.secho('creating new database container', fg='green')
    pull_db(client, path)

    click.secho('sync and migrate database', fg='green')

    if is_windows():
        # interactive mode is not yet supported with docker-compose
        # on windows. that's why we have to call it as daemon
        # and just wait a sane time
        check_call(docker_compose('run', '-d', 'web', 'start', 'migrate'))
        sleep(30)
    else:
        check_call(docker_compose('run', 'web', 'start', 'migrate'))


def create_workspace(client, website_slug, path=None):
    click.secho('Creating workspace...', fg='green')

    path = os.path.abspath(
        os.path.join(path, website_slug)
        if path else website_slug
    )

    if os.path.exists(path) and (not os.path.isdir(path) or os.listdir(path)):
        if click.confirm(
                'The path {} already exists and is not an empty directory. '
                'Do you want to remove it and continue?'.format(path)
        ):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        else:
            click.secho('Aborting', fg='red')
            exit(-1)

    # clone git project
    clone_project(website_slug, path)

    # check for new baseproject + add .aldryn
    configure_project(website_slug, path, client)

    # setup docker website containers
    setup_website_containers(client, path)

    # download media files
    pull_media(client, path)

    instructions = (
        "Finished setting up your project's workspace!",
        "To start the project, please:",
        " - change directory into '{}'".format(path),
        " - run 'aldryn project up'",
    )

    click.secho('\n\n{}'.format(os.linesep.join(instructions)), fg='green')


def pull_db(client, path=None):
    path = path or utils.get_project_home(path)
    website_id = utils.get_aldryn_project_settings(path)['id']
    website_slug = utils.get_aldryn_project_settings(path)['slug']
    docker_compose = utils.get_docker_compose_cmd(path)
    stage = 'test'

    click.secho(
        ' ===> Pulling database from {} {} server'.format(
            website_slug,
            stage,
        ),
    )
    start_time = time()

    # start db
    start_db = time()
    click.secho(' ---> Starting local database server...')
    click.secho('      ', nl=False)
    check_call(docker_compose('up', '-d', 'db'))
    # get db container id
    db_container_id = utils.get_db_container_id(path)
    db_time = int(time() - start_db)
    click.secho('      [{}s]'.format(db_time))

    click.secho(' ---> Preparing download...', nl=False)
    start_preparation = time()
    response = client.download_db_request(website_id) or {}
    progress_url = response.get('progress_url')
    if not progress_url:
        click.secho(' error!', color='red')
        exit()

    progress = {'success': None}
    while progress.get('success') is None:
        sleep(2)
        progress = client.download_db_progress(url=progress_url)
    if not progress.get('success'):
        click.secho(' error!', color='red')
        click.secho(progress.get('result') or '')
        exit()
    download_url = progress.get('result') or None
    preparation_time = int(time() - start_preparation)
    click.echo(' [{}s]'.format(preparation_time))

    click.secho(' ---> Downloading database...', nl=False)
    start_download = time()
    db_dump_path = client.download_db(website_slug, url=download_url, directory=path)
    download_time = int(time() - start_download)
    click.echo(' [{}s]'.format(download_time))

    # strip path from dump_path for use in the docker container
    db_dump_path = db_dump_path.replace(path, '')
    click.secho(' ---> Waiting for local database server...', nl=False)
    start_wait = time()
    # check for postgres in db container to start
    attempts = 10
    for attempt in range(attempts):
        try:
            check_call([
                'docker', 'exec', db_container_id,
                'psql', '-U', 'postgres',
            ], catch=False, silent=True)
        except subprocess.CalledProcessError:
            sleep(5)
        else:
            break
    else:
        exit(
            "Couldn't connect to database container. "
            "Database server may not have started."
        )
    wait_time = int(time() - start_wait)
    click.echo(' [{}s]'.format(wait_time))

    click.secho(' ---> Removing local database...', nl=False)
    start_remove = time()
    # create empty db
    subprocess.call([
        'docker', 'exec', db_container_id,
        'dropdb', '-U', 'postgres', 'db', '--if-exists',
    ])  # TODO: silence me

    check_call([
        'docker', 'exec', db_container_id,
        'createdb', '-U', 'postgres', 'db',
    ])
    # Workaround to add the hstore extension
    # TODO: solve extensions in a generic way in harmony with server side db-api
    check_call([
        'docker', 'exec', db_container_id,
        'psql', '-U', 'postgres', '--dbname=db',
        '-c', 'CREATE EXTENSION IF NOT EXISTS hstore;',
    ])
    remove_time = int(time() - start_remove)
    click.echo(' [{}s]'.format(remove_time))

    click.secho(' ---> Importing database...', nl=False)
    start_import = time()
    # TODO: use same dump-type detection like server side on db-api
    try:
        piped_restore = (
            'tar -xzOf /app/{}'
            ' | pg_restore -U postgres --dbname=db -n public '
            '--no-owner --exit-on-error'
            .format(db_dump_path)
        )
        subprocess.call((
            'docker', 'exec', db_container_id,
            '/bin/bash', '-c', piped_restore,
        ))
    except subprocess.CalledProcessError:
        pass
    import_time = int(time() - start_import)
    click.echo(' [{}s]'.format(import_time))

    click.secho('Done', fg='green', nl=False)
    total_time = int(time() - start_time)
    click.echo(' [{}s]'.format(total_time))


def pull_media(client, path=None):
    project_home = utils.get_project_home(path)
    path = os.path.join(project_home, 'data', 'media')
    website_id = utils.get_aldryn_project_settings(path)['id']
    website_slug = utils.get_aldryn_project_settings(path)['slug']
    stage = 'test'

    click.secho(
        ' ===> Pulling media files from {} {} server'.format(
            website_slug,
            stage,
        ),
    )
    start_time = time()
    click.secho(' ---> Preparing download...', nl=False)
    start_preparation = time()
    response = client.download_media_request(website_id) or {}
    progress_url = response.get('progress_url')
    if not progress_url:
        click.secho(' error!', color='red')
        exit()

    progress = {'success': None}
    while progress.get('success') is None:
        sleep(2)
        progress = client.download_media_progress(url=progress_url)
    if not progress.get('success'):
        click.secho(' error!', color='red')
        click.secho(progress.get('result') or '')
        exit()
    download_url = progress.get('result') or None
    preparation_time = int(time() - start_preparation)
    click.echo(' [{}s]'.format(preparation_time))

    click.secho(' ---> Downloading...', nl=False)
    start_download = time()
    backup_path = client.download_media(website_slug, url=download_url)
    if not backup_path:
        # no backup yet, skipping
        return
    download_time = int(time() - start_download)
    click.echo(' [{}s]'.format(download_time))

    if os.path.isdir(path):
        start_remove = time()
        click.secho(' ---> Removing local files...', nl=False)
        shutil.rmtree(path)
        remove_time = int(time() - start_remove)
        click.echo(' [{}s]'.format(remove_time))

    if 'linux' in sys.platform:
        # On Linux, Docker typically runs as root, so files and folders
        # created from within the container will be owned by root. As a
        # workaround, make the folder permissions more permissive, to
        # allow the invoking user to create files inside it.
        docker_compose = utils.get_docker_compose_cmd(project_home)
        check_call(
            docker_compose(
                'run', '--rm', 'web',
                'chown', '-R', str(os.getuid()), 'data'
            )
        )

    click.secho(' ---> Extracting files to {}...'.format(path), nl=False)
    start_extract = time()
    with open(backup_path, 'rb') as fobj:
        with tarfile.open(fileobj=fobj, mode='r:*') as media_archive:
            media_archive.extractall(path=path)
    os.remove(backup_path)
    extract_time = int(time() - start_extract)
    click.echo(' [{}s]'.format(extract_time))
    click.secho('Done', fg='green', nl=False)
    total_time = int(time() - start_time)
    click.echo(' [{}s]'.format(total_time))


def push_db(client):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)['id']
    dump_filename = 'local_db.sql'
    archive_filename = 'local_db.tar.gz'
    archive_path = os.path.join(project_home, archive_filename)
    docker_compose = utils.get_docker_compose_cmd(project_home)
    website_slug = utils.get_aldryn_project_settings(project_home)['slug']
    stage = 'test'

    click.secho(
        ' ===> Pushing local database to {} {} server'.format(
            website_slug,
            stage,
        ),
    )
    start_time = time()

    # start db
    start_db = time()
    click.secho(' ---> Starting local database server...')
    click.secho('      ', nl=False)
    check_call(docker_compose('up', '-d', 'db'))
    db_time = int(time() - start_db)
    click.secho('      [{}s]'.format(db_time))

    # take dump of database
    click.secho(' ---> Dumping local database...', nl=False)
    start_dump = time()
    # TODO: show total table and row count
    db_container_id = utils.get_db_container_id(project_home)
    subprocess.call((
        'docker', 'exec', db_container_id,
        'pg_dump', '-U', 'postgres', '-d', 'db',
        '--no-owner', '--no-privileges',
        '-f', os.path.join('/app/', dump_filename)
    ))
    dump_time = int(time() - start_dump)
    click.echo(' [{}s]'.format(dump_time))

    sql_dump_size = os.path.getsize(dump_filename)
    click.secho(
        ' ---> Compressing SQL dump ({})...'.format(
            pretty_size(sql_dump_size)
        ),
        nl=False,
    )
    start_compress = time()
    with tarfile.open(archive_path, mode='w:gz') as tar:
        tar.add(
            os.path.join(project_home, dump_filename),
            arcname=dump_filename
        )
    compressed_size = os.path.getsize(archive_filename)
    compress_time = int(time() - start_compress)
    click.echo(
        ' {} [{}s]'.format(
            pretty_size(compressed_size),
            compress_time,
        )
    )

    click.secho(' ---> Uploading...', nl=False)
    start_upload = time()
    response = client.upload_db(website_id, archive_path) or {}
    upload_time = int(time() - start_upload)
    click.echo(' [{}s]'.format(upload_time))

    progress_url = response.get('progress_url')
    if not progress_url:
        click.secho(' error!', color='red')
        exit()

    click.secho(' ---> Processing...', nl=False)
    start_processing = time()
    progress = {'success': None}
    while progress.get('success') is None:
        sleep(2)
        progress = client.upload_db_progress(url=progress_url)
    if not progress.get('success'):
        click.secho(' error!', color='red')
        click.secho(progress.get('result') or '')
        exit()
    processing_time = int(time() - start_processing)
    click.echo(' [{}s]'.format(processing_time))

    # clean up
    for temp_file in (dump_filename, archive_filename):
        os.remove(os.path.join(project_home, temp_file))
    click.secho('Done', fg='green', nl=False)
    total_time = int(time() - start_time)
    click.echo(' [{}s]'.format(total_time))


def push_media(client):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)['id']
    archive_path = os.path.join(project_home, 'local_media.tar.gz')
    website_slug = utils.get_aldryn_project_settings(project_home)['slug']
    stage = 'test'
    click.secho(
        ' ---> Pushing local media to {} {} server'.format(
            website_slug,
            stage,
        ),
    )
    start_time = time()
    click.secho('Compressing local media folder...',  nl=False)
    uncompressed_size = 0
    start_compression = time()
    with tarfile.open(archive_path, mode='w:gz') as tar:
        media_dir = os.path.join(project_home, 'data', 'media')
        for item in os.listdir(media_dir):
            if item == 'MANIFEST':
                # partial uploads are currently not supported
                # not including MANIFEST to do a full restore
                continue
            file_path = os.path.join(media_dir, item)
            tar.add(file_path, arcname=item)
            uncompressed_size += get_size(file_path)
        file_count = len(tar.getmembers())
    compress_time = int(time() - start_compression)
    click.echo(
        ' {} {} ({}) compressed to {} [{}s]'.format(
            file_count,
            'files' if file_count > 1 else 'file',
            pretty_size(uncompressed_size),
            pretty_size(os.path.getsize(archive_path)),
            compress_time,
        )
    )
    click.secho('Uploading...', nl=False)
    start_upload = time()
    response = client.upload_media(website_id, archive_path) or {}
    upload_time = int(time() - start_upload)
    click.echo(' [{}s]'.format(upload_time))
    progress_url = response.get('progress_url')
    if not progress_url:
        click.secho(' error!', color='red')
        exit()

    click.secho('Processing...', nl=False)
    start_processing = time()
    progress = {'success': None}
    while progress.get('success') is None:
        sleep(2)
        progress = client.upload_media_progress(url=progress_url)
    if not progress.get('success'):
        click.secho(' error!', color='red')
        click.secho(progress.get('result') or '')
        exit()
    processing_time = int(time() - start_processing)
    click.echo(' [{}s]'.format(processing_time))

    # clean up
    os.remove(archive_path)
    click.secho('Done', fg='green', nl=False)
    total_time = int(time() - start_time)
    click.echo(' [{}s]'.format(total_time))


def update_local_project():
    project_home = utils.get_project_home()
    docker_compose = utils.get_docker_compose_cmd(project_home)

    click.secho('Pulling changes from git remote', fg='green')
    check_call(('git', 'pull'))
    click.secho('Pulling docker images', fg='green')
    check_call(docker_compose('pull'))
    click.secho('Building local docker images', fg='green')
    check_call(docker_compose('build'))


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

        check_call(docker_compose('build', 'web'))

    click.secho(
        'The package {} has been added to your local development project!'
        .format(package)
    )


def open_project(open_browser=True):
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    try:
        addr = check_output(docker_compose('port', 'web', '80'), catch=False)
    except subprocess.CalledProcessError:
        if click.prompt('Your project is not running. Do you want to start '
                        'it now?'):
            return start_project()
        return
    host, port = addr.rstrip(os.linesep).split(':')

    if host == '0.0.0.0':
        docker_host_url = os.environ.get('DOCKER_HOST')
        if docker_host_url:
            proto, host_port = os.environ.get('DOCKER_HOST').split('://')
            host = host_port.split(':')[0]

    addr = 'http://{}:{}/'.format(host, port)

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
            click.echo()
            break
    else:
        raise click.ClickException(
            "\nProject failed to start. Please run 'docker-compose logs' "
            "to get more information."
        )

    if open_browser:
        click.launch(addr)
    return addr


def start_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    try:
        check_output(docker_compose('up', '-d'), catch=False, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        output = exc.output.decode()
        if 'port is already allocated' in output:
            click.secho(
                "There's already another program running on this project's "
                "port. Please either stop the other program or change the "
                "port in the 'docker-compose.yml' file and try again.\n",
                fg='red'
            )
        raise click.ClickException(output)

    return open_project(open_browser=True)


def show_project_status():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    check_call(docker_compose('ps'))


def stop_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    check_call(docker_compose('stop'))
