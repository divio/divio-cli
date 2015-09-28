import re
import os
import subprocess

import click

from ..utils import dev_null
from . import utils


GIT_CLONE_URL = 'git@git.aldryn.com:{slug}.git'


def get_docker_compose_cmd(path):
    docker_compose_base = [
        'docker-compose', '-f', os.path.join(path, 'docker-compose.yml')
    ]

    def docker_compose(*commands):
        return docker_compose_base + [cmd for cmd in commands]

    return docker_compose


def create_workspace(client, website_slug, path=None):
    path = os.path.abspath(
        os.path.join(path, website_slug)
        if path else website_slug
    )

    docker_compose = get_docker_compose_cmd(path)

    website_git_path = GIT_CLONE_URL.format(slug=website_slug)

    existing_db_container_id = subprocess.check_output(
        docker_compose('ps', '-q', 'db')
    ).replace(os.linesep, '')

    reuse_db_container = False
    if existing_db_container_id:
        # get db container id
        reuse_db_container = click.confirm(
            "There's an existing database container for this "
            "project ({}). Do you want to reuse this container?"
            .format(existing_db_container_id),
            default=True,
        )

    try:
        click.echo(' - cloning project repository')
        clone_args = ['git', 'clone', website_git_path]
        if path:
            clone_args.append(path)
        subprocess.check_output(clone_args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(exc.output)

    click.echo('\nCreating workspace...')

    # stop all running for project
    subprocess.check_output(docker_compose('stop'))

    # pull docker images
    click.echo(' - downloading remote docker images')
    subprocess.check_output(docker_compose('pull'), stderr=subprocess.STDOUT)

    # build docker images
    click.echo(' - building local docker images')
    subprocess.check_output(docker_compose('build'), stderr=subprocess.STDOUT)

    if existing_db_container_id and not reuse_db_container:
        click.echo(' - removing old database container')
        subprocess.check_output(
            docker_compose('stop', 'db'),
            stderr=subprocess.STDOUT,
        )
        subprocess.check_output(
            docker_compose('rm', '-f', 'db'),
            stderr=subprocess.STDOUT,
        )

    if not reuse_db_container:
        click.echo(' - creating new database container')

        # start db
        subprocess.check_output(
            docker_compose('up', '-d', '--force-recreate', 'db'),
            stderr=subprocess.STDOUT,
        )

        # get db container id
        db_container_id = subprocess.check_output(
            docker_compose('ps', '-q', 'db'),
            stderr=subprocess.STDOUT,
        ).replace(os.linesep, '')

        click.echo(' - fetching database dump')
        db_dump_path = client.download_db(website_slug, directory=path)
        # strip path from dump_path for use in the docker container
        db_dump_path = db_dump_path.replace(path, '')

        # create empty db
        subprocess.check_output([
            'docker', 'exec', db_container_id,
            'createdb', '-U', 'postgres', 'db',
        ], stderr=subprocess.STDOUT)

        click.echo(' - inserting database dump')
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
        subprocess.check_output(
            docker_compose('stop'), stderr=subprocess.STDOUT
        )

    instructions = [
        "Finished setting up your project's workspace!",
        "To start the project, please:",
    ]

    if path:
        instructions.append(' - change directory into {}'.format(path))
    instructions.append(' - run docker-compose up')

    click.secho('\n\n{}'.format(os.linesep.join(instructions)), fg='green')


def develop_package(package):
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

    # build web again
    docker_compose = get_docker_compose_cmd(project_home)

    try:
        subprocess.check_output(
            docker_compose('build', 'web'),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(exc.output)

    click.secho(
        'The package {} has been added to your local development project!'
        .format(package)
    )
