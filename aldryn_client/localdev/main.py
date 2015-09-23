import os
import subprocess

import click

from ..utils import dev_null


GIT_CLONE_URL = 'git@git.aldryn.com:{slug}.git'


def get_docker_compose_cmd(path):
    docker_compose_base = [
        'docker-compose', '-f', os.path.join(path, 'docker-compose.yml')
    ]

    def docker_compose(cmd):
        if not isinstance(cmd, list):
            cmd = [cmd]
        return docker_compose_base + cmd

    return docker_compose


def create_workspace(client, website_slug, path=None):
    path = os.path.abspath(
        os.path.join(path, website_slug)
        if path else website_slug
    )

    docker_compose = get_docker_compose_cmd(path)

    website_git_path = GIT_CLONE_URL.format(slug=website_slug)
    website_id = client.get_website_id_for_slug(website_slug)
    db_data_container = 'aldryn_{}_dbdata'.format(website_id)

    existing_db_data_container_id = subprocess.check_output([
        'docker', 'ps', '-a', '-q',
        '--filter=name={}'.format(db_data_container),
    ]).replace(os.linesep, '')

    reuse_db_data_container = False
    if existing_db_data_container_id:
        # get db container id
        reuse_db_data_container = click.confirm(
            "There's an existing database storage container for this "
            "project ({}). Do you want to reuse this container?"
            .format(existing_db_data_container_id),
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
    click.echo(' - creating database storage container')
    if existing_db_data_container_id and not reuse_db_data_container:
        click.echo(' - removing old database container')
        subprocess.check_output(
            docker_compose(['stop', 'db']),
            stderr=subprocess.STDOUT,
        )
        subprocess.check_output(
            docker_compose(['rm', '-f', 'db']),
            stderr=subprocess.STDOUT,
        )

        click.echo(' - removing old database storage container')
        subprocess.check_output(
            ('docker', 'rm', '-f', db_data_container),
            stderr=subprocess.STDOUT,
        )

    if not reuse_db_data_container:
        click.echo(' - creating new database storage container')
        subprocess.check_output([
            'docker', 'run', '--name', db_data_container,
            'aldryn/open-postgres:latest', '/bin/true',
        ], stderr=subprocess.STDOUT)

    # stop all running for project
    subprocess.check_output(docker_compose('stop'))

    # pull docker images
    click.echo(' - downloading remote docker images')
    subprocess.check_output(docker_compose('pull'), stderr=subprocess.STDOUT)

    # build docker images
    click.echo(' - building local docker images')
    subprocess.check_output(docker_compose('build'), stderr=subprocess.STDOUT)

    if not reuse_db_data_container:
        # start db
        subprocess.check_output(
            docker_compose(['up', '-d', '--force-recreate', 'db']),
            stderr=subprocess.STDOUT,
        )

        # get db container id
        db_container_id = subprocess.check_output(
            docker_compose(['ps', '-q', 'db']),
            stderr=subprocess.STDOUT,
        ).replace(os.linesep, '')

        click.echo(' - fetching database dump')
        client.download_db(website_slug, target_path=path)

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
                subprocess.call([
                    'docker', 'exec', db_container_id,
                    'pg_restore',
                    '-U', 'postgres',
                    '-d', 'db',
                    '/app/database.dump',
                ], stdout=devnull, stderr=devnull)
            except subprocess.CalledProcessError:
                pass

        # stop db
        subprocess.check_output(
            docker_compose(['stop']), stderr=subprocess.STDOUT
        )

    instructions = [
        "Finished setting up your project's workspace!",
        "To start the project, please:",
    ]

    if path:
        instructions.append(' - change directory into {}'.format(path))
    instructions.append(' - run docker-compose up')

    click.secho('\n\n{}'.format(os.linesep.join(instructions)), fg='green')

