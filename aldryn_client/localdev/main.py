import os
import subprocess

import click


def create_workspace(client, website_slug, path=None):
    website_git_path = 'git@github.com:aldryn/test-project.git'  # temporary

    path = os.path.abspath(path) if path else None
    website_id = client.get_website_id_for_slug(website_slug)

    docker_compose_base = [
        'docker-compose', '-f', os.path.join(path, 'docker-compose.yml')
    ]

    def docker_compose(cmd):
        if not isinstance(cmd, list):
            cmd = [cmd]
        return docker_compose_base + cmd

    try:
        # clone project
        clone_args = ['git', 'clone', website_git_path]
        if path:
            clone_args.append(path)
        subprocess.check_output(clone_args)

    except subprocess.CalledProcessError as exc:
        raise click.ClickException(exc.output)

    # create postgres data container
    dbdata_container = 'aldryn_{}_dbdata'.format(website_id)

    existing_data_container_id = subprocess.check_output([
        'docker', 'ps', '-a', '-q',
        '--filter=name={}'.format(dbdata_container),
    ]).replace(os.linesep, '')

    reuse_data_container = False
    if existing_data_container_id:
        reuse_data_container = click.confirm(
            'There\'s an existing database container for this project '
            '({}). Do you want to reuse this container?'
            .format(existing_data_container_id),
            default=True,
        )

        if not reuse_data_container:
            subprocess.check_output([
                'docker', 'rm', '-f', existing_data_container_id,
            ])

    if not reuse_data_container:
        subprocess.check_output([
            'docker', 'run', '--name', dbdata_container,
             'aldryn/open-postgres:latest', '/bin/true',
        ])

    # pull docker images
    subprocess.check_output(docker_compose('pull'))

    # build docker images
    subprocess.check_output(docker_compose('build'))

    if not reuse_data_container:
        # load database dump
        client.download_db()
        subprocess.check_output(
            docker_compose([
                'run', 'db', 'pg_restore', '-d', 'db',
                '/app/database.dump',
            ])
        )

    instructions = [
        'Finished setting up your project\'s workspace!',
        'To start the project, please:',
    ]

    if path:
        instructions.append(' * change directory into {}'.format(path))
    instructions.append(' * run docker-compose up')

    click.secho(os.linesep.join(instructions), fg='green')
