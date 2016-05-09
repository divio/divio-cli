import json
import subprocess
import itertools
import os
import sys
from distutils.version import StrictVersion

try:
    import ipdb as pdb
except ImportError:
    import pdb

import click

from . import localdev
from .localdev.utils import get_aldryn_project_settings
from .cloud import CloudClient, get_endpoint
from .check_system import check_requirements, check_requirements_human
from .utils import (
    hr, table, open_project_cloud_site, get_dashboard_url,
    get_project_cheatsheet_url, get_latest_version_from_pypi,
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

    ctx.obj = CloudClient(get_endpoint())

    # skip if 'aldryn version' is run
    if not ctx.args == ['version']:
        # check for newer versions
        ctx.obj.config.check_for_updates()


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
@click.option(
    '-g', '--grouped', is_flag=True, default=False,
    help='Group by organisation'
)
@click.pass_obj
def project_list(obj, grouped):
    """List all your projects"""
    api_response = obj.get_projects()
    header = ('Slug', 'Name', 'Organisation')

    # get all users + organisations
    groups = {
        'users': {
            account['id']: {'name': 'Personal', 'projects': []}
            for account in api_response['accounts']
            if account['type'] == 'user'
        },
        'organisations': {
            account['id']: {'name': account['name'], 'projects': []}
            for account in api_response['accounts']
            if account['type'] == 'organisation'
        }
    }

    # sort websites into groups
    for website in api_response['websites']:
        organisation_id = website['organisation_id']
        if organisation_id:
            owner = groups['organisations'][website['organisation_id']]
        else:
            owner = groups['users'][website['owner_id']]
        owner['projects'].append((website['domain'], website['name']))

    accounts = itertools.chain(
        groups['users'].items(),
        groups['organisations'].items()
    )

    def sort_projects(items):
        return sorted(items, key=lambda x: x[0].lower())

    # print via pager
    if grouped:
        output_items = []
        for group, data in accounts:
            projects = data['projects']
            if projects:
                output_items.append(
                    u'{title}\n{line}\n\n{table}\n\n'.format(
                        title=data['name'],
                        line='=' * len(data['name']),
                        table=table(sort_projects(projects), header[:2])
                    )
                )
        output = os.linesep.join(output_items).rstrip(os.linesep)
    else:
        # add account name to all projects
        projects = [
            each + (data['name'],) for group, data in accounts
            for each in data['projects']
        ]
        output = table(sort_projects(projects), header)

    click.echo_via_pager(output)


# @project.command(name='info')
# @click.argument('slug')
# @click.pass_obj
# def project_info(obj, slug):
#     """Show info about a project"""
#     # TODO: proper formatting
#     website_id = obj.get_website_id_for_slug(slug)
#     click.echo(obj.get_project(website_id))


@project.command(name='deploy')
@click.argument('stage', default='test')
@click.pass_obj
def project_deploy(obj, stage):
    """Deploy project"""
    website_id = get_aldryn_project_settings()['id']
    obj.deploy_project_or_get_progress(website_id, stage)


@project.command(name='dashboard')
@click.pass_obj
def project_dashboard(obj):
    """Open project dashboard"""
    click.launch(get_dashboard_url(obj))


@project.command(name='up')
@click.pass_obj
def project_up(obj):
    """Start local project"""
    localdev.start_project()


@project.command(name='open')
@click.pass_obj
def project_open(obj):
    """Open local project in browser"""
    localdev.open_project()


@project.command(name='update')
@click.pass_obj
def project_update(obj):
    """Update project with latest changes from the Cloud"""
    localdev.update_local_project()


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
    localdev.show_project_status()


@project.command(name='stop')
@click.pass_obj
def project_stop(obj):
    """Stop local project"""
    localdev.stop_project()


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
    if not check_requirements_human(silent=True):
        click.secho(
            "There was a problem while checking your system. Please run "
            "'aldryn doctor'.", fg='red'
        )
        sys.exit(1)

    localdev.create_workspace(obj, slug, path)


@project.group(name='pull')
def project_pull():
    """Pull db or files from Aldryn"""
    pass


@project_pull.command(name='db')
@click.pass_obj
def pull_db(obj):
    localdev.pull_db(obj)


@project_pull.command(name='media')
@click.pass_obj
def pull_media(obj):
    localdev.pull_media(obj)


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

        '\nIt is recommended to go the project settings on control.aldryn.com',
        'and take a backup before restoring the database. You can find this ',
        'action in the "Manage Project" section.',

        '\nPlease proceed with caution!'
    )

    click.secho(os.linesep.join(warning), fg='red')
    if not click.confirm('\nAre you sure you want to continue?'):
        return
    localdev.push_db(obj)


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

        '\nIt is recommended to go the project settings on control.aldryn.com',
        'and take a backup before restoring media files. You can find this ',
        'action in the "Manage Project" section.',

        '\nPlease proceed with caution!'
    )

    click.secho(os.linesep.join(warning), fg='red')
    if not click.confirm('\nAre you sure you want to continue?'):
        return
    localdev.push_media(obj)


@project.command(name='develop')
@click.argument('package')
@click.option(
    '--no-rebuild', is_flag=True, default=False, help='Addon directory'
)
@click.pass_obj
def project_develop(obj, package, no_rebuild):
    """Add a package 'package' to your local project environment"""
    localdev.develop_package(package, no_rebuild)


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


@addon.command(name='register')
@click.argument('verbose_name')
@click.argument('package_name')
@click.option('-o', '--organisation', help='Register for an organisation', type=int)
@click.pass_context
def addon_register(ctx, package_name, verbose_name, organisation):
    """Register your addon on Aldryn\n
    - Verbose Name:        Name of the Addon as it appears in the Marketplace.
    - Package Name:        System wide unique Python package name
    """
    ret = ctx.obj.register_addon(package_name, verbose_name, organisation)
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
    help="don't check PyPI for newer version",
)
@click.option(
    '-e', '--show-error',  is_flag=True, default=False,
    help="show error if PyPI check fails",
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
        current_version = StrictVersion(__version__)
        newest_version, exc = get_latest_version_from_pypi()

        if newest_version and newest_version == current_version:
            click.echo('\nYou have the latest version of aldryn-client!')

        elif newest_version and newest_version > current_version:
            click.echo(
                "\nNew version ({newest_version}) available on PyPI. Update "
                "now using 'pip install aldryn-client=={newest_version}'"
                .format(newest_version=newest_version)
            )
        elif newest_version is False:
            if show_error:
                click.secho(
                    'There was an error while trying to check for the latest '
                    'version on pypi.python.org',
                    fg='red'
                )
                if exc:
                    click.echo(exc)


@cli.command()
@click.option(
    '-m', '--machine-readable', is_flag=True, default=False,
)
@click.option('-c', '--checks', default=None)
def doctor(machine_readable, checks):
    """Check if your system meets the requirements
    for Aldryn local development"""

    if checks:
        checks = checks.split(',')

    if machine_readable:
        errors = {
            check: error
            for check, check_name, error
            in check_requirements(checks)
        }
        exitcode = 1 if any(errors.values()) else 0
        click.echo(json.dumps(errors), nl=False)
    else:
        click.echo('Verifying your system setup')
        exitcode = 0 if check_requirements_human(checks) else 1

    sys.exit(exitcode)
