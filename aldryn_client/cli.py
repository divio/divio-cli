import sys

try:
    import ipdb as pdb
except ImportError:
    import pdb

import click

from .localdev.main import (
    create_workspace, develop_package, load_database_dump, start_project,
    open_project, stop_project
)
from .cloud import CloudClient
from .check_system import check_requirements
from .utils import hr, table
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

    ctx.obj = CloudClient()


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


@project.command(name='info')
@click.argument('slug')
@click.pass_obj
def project_info(obj, slug):
    """Show info about a project"""
    # TODO: proper formatting
    website_id = obj.get_website_id_for_slug(slug)
    click.echo(obj.get_project(website_id))


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


@project.command(name='stop')
@click.pass_obj
def project_stop(obj):
    """Stop local project"""
    stop_project()


@project.command(name='workon')
@click.argument('slug')
@click.option('-p', '--path', default='.', help='install project to path', type=click.Path(writable=True, readable=True))
@click.pass_obj
def project_workon(obj, slug, path):
    """Set up a development environment for an Aldryn Cloud project"""
    create_workspace(obj, slug, path)


@project.group(name='pull')
def project_pull():
    """Pull db or files from Aldryn"""
    pass


@project_pull.command(name='db')
@click.argument('slug')
@click.pass_obj
def pull_db(obj, slug):
    load_database_dump(obj, slug)


@project.command(name='develop')
@click.argument('package', 'package')
@click.option('--no-rebuild', is_flag=True, default=False, help='Addon directory')
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


@cli.command(name='check-system')
def check_system():
    """Check if your system meets the requirements for Aldryn local development"""
    click.echo('Verifying your system\'s setup')
    check_requirements()
