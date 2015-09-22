import sys

try:
    import ipdb as pdb
except ImportError:
    import pdb

import click

from .cloud import CloudClient
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
    click.echo(obj.login(token))


@cli.group()
def project():
    pass


@project.command(name='list')
@click.pass_obj
def project_list(obj):
    data = obj.get_projects()

    organisations = {
        account['id']: account['name']
        for account in data['accounts']
        if account['type'] == 'organisation'
    }

    projects = [(
        project_data['id'],
        project_data['name'],
        organisations.get(project_data['organisation_id'], 'Personal'),
    ) for project_data in data['websites']]

    header = ['ID', 'Name', 'Organisation']
    click.echo(table(projects, header))


@project.command(name='info')
@click.argument('project_id', 'id')
@click.pass_obj
def project_info(obj, project_id):
    # TODO: proper formatting
    click.echo(obj.get_project(project_id))


@cli.group()
@click.option('-p', '--path', default='.', help='Addon directory')
@click.pass_obj
def addon(obj, path):
    pass


@addon.command(name='validate')
@click.pass_context
def addon_validate(ctx):
    validate_addon(ctx.parent.params['path'])
    click.echo('Addon is valid!')


@addon.command(name='upload')
@click.pass_context
def addon_upload(ctx):
    ret = upload_addon(ctx.obj, ctx.parent.params['path'])
    click.echo(ret)


@cli.group()
@click.option('-p', '--path', default='.', help='Boilerplate directory')
@click.pass_obj
def boilerplate(obj, path):
    pass


@boilerplate.command(name='validate')
@click.pass_context
def boilerplate_validate(ctx):
    validate_boilerplate(ctx.parent.params['path'])
    click.echo('Boilerplate is valid!')


@boilerplate.command(name='upload')
@click.pass_context
def boilerplate_upload(ctx):
    ret = upload_boilerplate(ctx.obj, ctx.parent.params['path'])
    click.echo(ret)

