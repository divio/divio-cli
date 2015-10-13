import subprocess
import os
import sys
from distutils.version import StrictVersion

try:
    import ipdb as pdb
except ImportError:
    import pdb

import click
import requests

from .localdev.main import (
    create_workspace, develop_package, start_project, open_project,
    stop_project, load_database_dump, download_media, upload_database,
    upload_media, show_project_status, update_local_project,
)
from .cloud import CloudClient, get_aldryn_host
from .check_system import check_requirements
from .utils import (
    hr, table, open_project_cloud_site, get_dashboard_url,
    get_project_cheatsheet_url,
)
from .validators.addon import validate_addon
from .validators.boilerplate import validate_boilerplate
from .upload.addon import upload_addon
from .upload.boilerplate import upload_boilerplate


@click.group()
@click.option('-d', '--debug/--no-debug', default=False,
              help=('Drop into the debugger if the command execution raises '
                    'an exception.'))
@click.pass_context
def cli(ctx, debug):
    if debug:
        def exception_handler(type, value, traceback):
            click.secho(
                '\nAn exception occurred while executing the requested '
                'command:', fg='red'
            )
            hr(fg='red')
            sys.__excepthook__(type, value, traceback)
            click.secho('\nStarting interactive debugging session:', fg='red')
            hr(fg='red')
            pdb.post_mortem(traceback)
        sys.excepthook = exception_handler

    ctx.obj = CloudClient(get_aldryn_host())


def login_token_helper(ctx, param, value):
    if not value:
        url = ctx.obj.get_access_token_url()
        click.secho('Your browser has been opened to visit: {}'.format(url))
        click.launch(url)
        value = click.prompt('Please copy the access token and paste it here')
    return value


@cli.command()
@click.argument('token', required=False, callback=login_token_helper)
@click.pass_obj
def login(obj, token):
    """Authorize your machine with Aldryn"""
    click.echo(obj.login(token))


@cli.group()
def project():
    """Manage your projects"""
    pass


@project.command(name='list')
@click.pass_obj
def project_list(obj):
    """List all your projects"""
    data = obj.get_projects()

    organisations = {
        account['id']: account['name']
        for account in data['accounts']
        if account['type'] == 'organisation'
    }

    projects = [(
        project_data['domain'],
        project_data['name'],
        organisations.get(project_data['organisation_id'], 'Personal'),
    ) for project_data in data['websites']]

    header = ['Slug', 'Name', 'Organisation']
    click.echo_via_pager(table(projects, header))


# @project.command(name='info')
# @click.argument('slug')
# @click.pass_obj
# def project_info(obj, slug):
#     """Show info about a project"""
#     # TODO: proper formatting
#     website_id = obj.get_website_id_for_slug(slug)
#     click.echo(obj.get_project(website_id))


@project.command(name='dashboard')
@click.pass_obj
def project_dashboard(obj):
    """Open project dashboard"""
    click.launch(get_dashboard_url(obj))


@project.command(name='up')
@click.pass_obj
def project_up(obj):
    """Start local project"""
    start_project()


@project.command(name='open')
@click.pass_obj
def project_open(obj):
    """Open local project in browser"""
    open_project()


@project.command(name='update')
@click.pass_obj
def project_update(obj):
    """Update project with latest changes from the Cloud"""
    update_local_project()


@project.command(name='test')
@click.pass_obj
def project_open_test(obj):
    """Open project test site"""
    open_project_cloud_site(obj, 'test')


@project.command(name='live')
@click.pass_obj
def project_open_live(obj):
    """Open project live site"""
    open_project_cloud_site(obj, 'live')


@project.command(name='status')
@click.pass_obj
def project_status(obj):
    """Show local project status"""
    show_project_status()


@project.command(name='stop')
@click.pass_obj
def project_stop(obj):
    """Stop local project"""
    stop_project()


@project.command(name='cheatsheet')
@click.pass_obj
def project_cheatsheet(obj):
    """Show useful commands for your project"""
    click.launch(get_project_cheatsheet_url(obj))


@project.command(name='setup')
@click.argument('slug')
@click.option(
    '-p', '--path', default='.', help='install project to path',
    type=click.Path(writable=True, readable=True)
)
@click.pass_obj
def project_setup(obj, slug, path):
    """Set up a development environment for an Aldryn project"""
    if not check_requirements(silent=True):
        click.secho(
            "There was a problem while checking your system. Please run "
            "'aldryn doctor'.", fg='red'
        )
        exit(1)

    create_workspace(obj, slug, path)


@project.group(name='pull')
def project_pull():
    """Pull db or files from Aldryn"""
    pass


@project_pull.command(name='db')
@click.pass_obj
def pull_db(obj):
    load_database_dump(obj)


@project_pull.command(name='media')
@click.pass_obj
def pull_media(obj):
    download_media(obj)


@project.group(name='push')
def project_push():
    """Push db or media files to Aldryn"""
    pass


@project_push.command(name='db')
@click.pass_obj
def push_db(obj):
    warning = (
        'WARNING',
        '=======',

        '\nYou are about to push your local database to the test server on ',
        'Aldryn. This will replace ALL data on the Aldryn test server with ',
        'the data you are about to push, including (but not limited to):',
        '  - User accounts',
        '  - CMS Pages & Plugins',

        '\nYou will also lose any changes that have been made on the test ',
        'server since you pulled its database to your local environment. ',

        '\nA database backup will be created before your Aldryn test server ',
        'database is overwritten, in case you need to undo this operation.',
        'You will find this database amongst other database backups in the ',
        '"Manage Project" section of the Aldryn Control Panel.',

        '\nPlease proceed with caution!'
    )

    click.secho(os.linesep.join(warning), fg='red')
    if not click.confirm('\nAre you sure you want to continue?'):
        return
    upload_database(obj)


@project_push.command(name='media')
@click.pass_obj
def push_media(obj):
    warning = (
        'WARNING',
        '=======',

        '\nYou are about to push your local media files to the test server on ',
        'Aldryn. This will replace ALL existing media files with the ones you ',
        'are about to push.',

        '\nYou will also lose any changes that have been made on the test ',
        'server since you pulled its files to your local environment. ',

        '\nA backup of all media files will be created before your Aldryn test ',
        'server media files are overwritten, in case you need to undo this operation.',
        'You will find this backup amongst other media file backups in the ',
        '"Manage Project" section of the Aldryn Control Panel.',

        '\nPlease proceed with caution!'
    )

    click.secho(os.linesep.join(warning), fg='red')
    if not click.confirm('\nAre you sure you want to continue?'):
        return

    upload_media(obj)


@project.command(name='develop')
@click.argument('package', 'package')
@click.option(
    '--no-rebuild', is_flag=True, default=False, help='Addon directory'
)
@click.pass_obj
def project_develop(obj, package, no_rebuild):
    """Add a package 'package' to your local project environment"""
    develop_package(package, no_rebuild)


@cli.group()
@click.option('-p', '--path', default='.', help='Addon directory')
@click.pass_obj
def addon(obj, path):
    """Validate and upload addon packages to Aldryn"""
    pass


@addon.command(name='validate')
@click.pass_context
def addon_validate(ctx):
    """Validate addon configuration"""
    validate_addon(ctx.parent.params['path'])
    click.echo('Addon is valid!')


@addon.command(name='upload')
@click.pass_context
def addon_upload(ctx):
    """Upload addon to Aldryn"""
    ret = upload_addon(ctx.obj, ctx.parent.params['path'])
    click.echo(ret)


@cli.group()
@click.option('-p', '--path', default='.', help='Boilerplate directory')
@click.pass_obj
def boilerplate(obj, path):
    """Validate and upload boilerplate packages to Aldryn"""
    pass


@boilerplate.command(name='validate')
@click.pass_context
def boilerplate_validate(ctx):
    """Validate boilerplate configuration"""
    validate_boilerplate(ctx.parent.params['path'])
    click.echo('Boilerplate is valid!')


@boilerplate.command(name='upload')
@click.pass_context
def boilerplate_upload(ctx):
    """Upload boilerplate to Aldryn"""
    ret = upload_boilerplate(ctx.obj, ctx.parent.params['path'])
    click.echo(ret)


@cli.command()
@click.option(
    '-s', '--skip-check',  is_flag=True, default=False,
    help="don't check PyPi for newer version",
)
@click.option(
    '-e', '--show-error',  is_flag=True, default=False,
    help="show error if PyPi check fails",
)
def version(skip_check, show_error):
    """Show version info"""
    from . import __version__
    click.echo('package version: {}'.format(__version__))

    # try to get git revision
    script_home = os.path.dirname(__file__)
    git_dir = os.path.join(script_home, '..', '.git')
    if os.path.exists(git_dir):
        revision = subprocess.check_output([
            'git', '--git-dir', git_dir,
            'rev-parse', '--short', 'HEAD'
        ]).strip()
        click.echo('git revision:    {}'.format(revision))

    if not skip_check:
        # check pypi for a newer version
        try:
            current_version = StrictVersion(__version__)
            response = requests.get(
                'https://pypi.python.org/pypi/aldryn-client/json'
            )
            response.raise_for_status()
            new_version = StrictVersion(response.json()['info']['version'])

            if new_version == current_version:
                click.echo('\nYou have the latest version of aldryn-client!')

            elif new_version > __version__:
                click.echo(
                    "\nNew version ({new_version}) available on PyPi. Update "
                    "now using 'pip install aldryn-client=={new_version}'"
                    .format(new_version=new_version)
                )
        except (requests.RequestException, KeyError, ValueError) as exc:
            if show_error:
                click.secho(
                    '\nThere was an error while trying to retrieve the latest '
                    'version from pypi.python.org:\n', fg='red'
                )
                click.echo(exc)


@cli.command()
def doctor():
    """Check if your system meets the requirements
    for Aldryn local development"""
    click.echo('Verifying your system setup')
    exit(0 if check_requirements() else 1)
