import json
import itertools
import os
import sys
import base64

try:
    import ipdb as pdb
except ImportError:
    import pdb

import click

from . import exceptions
from . import localdev
from . import messages
from . import crypto
from .localdev.utils import get_aldryn_project_settings
from .cloud import CloudClient, get_endpoint
from .check_system import check_requirements, check_requirements_human
from .utils import (
    hr, table, open_project_cloud_site,
    get_cp_url, get_git_checked_branch,
    print_package_renamed_warning,
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
    if sys.argv[0].endswith('aldryn'):
        print_package_renamed_warning()

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

    ctx.obj = CloudClient(get_endpoint(), debug)

    try:
        is_version_command = sys.argv[1] == 'version'
    except IndexError:
        is_version_command = False

    # skip if 'aldryn version' is run
    if not is_version_command:
        # check for newer versions
        update_info = ctx.obj.config.check_for_updates()
        if update_info['update_available']:
            click.secho(
                'New version {} is available. Type `divio version` to '
                'show information about upgrading.'
                .format(update_info['remote']),
                fg='yellow'
            )


def login_token_helper(ctx, value):
    if not value:
        url = ctx.obj.get_access_token_url()
        click.secho('Your browser has been opened to visit: {}'.format(url))
        click.launch(url)
        value = click.prompt('Please copy the access token and paste it here')
    return value


@cli.command()
@click.argument('token', required=False)
@click.option(
    '--check', is_flag=True, default=False,
    help='Check for current login status',
)
@click.pass_context
def login(ctx, token, check):
    """Authorize your machine with the Divio Cloud"""
    success = True
    if check:
        success, msg = ctx.obj.check_login_status()
    else:
        token = login_token_helper(ctx, token)
        msg = ctx.obj.login(token)

    click.echo(msg)
    sys.exit(0 if success else 1)


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
    click.launch(get_cp_url(obj))


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
    localdev.update_local_project(get_git_checked_branch())


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
    click.launch(get_cp_url(obj, 'local-development/'))


@project.command(name='setup')
@click.argument('slug')
@click.option(
    '-s', '--stage', default='test',
    help='pull data from stage (test or live)',
)
@click.option(
    '-p', '--path', default='.', help='install project to path',
    type=click.Path(writable=True, readable=True),
)
@click.option(
    '--overwrite', is_flag=True, default=False,
    help="Overwrite the project directory if it already exists",
)
@click.option(
    '--skip-doctor', is_flag=True, default=False,
    help='Skip system test before setting up the project',
)
@click.pass_obj
def project_setup(obj, slug, stage, path, overwrite, skip_doctor):
    """Set up a development environment for a Divio Cloud project"""
    if not skip_doctor and not check_requirements_human(
            config=obj.config, silent=True
    ):
        click.secho(
            "There was a problem while checking your system. Please run "
            "'divio doctor'.", fg='red'
        )
        sys.exit(1)

    localdev.create_workspace(obj, slug, stage, path, overwrite)


@project.group(name='pull')
def project_pull():
    """Pull db or files from the Divio Cloud"""
    pass


@project_pull.command(name='db')
@click.argument('stage', default='test')
@click.pass_obj
def pull_db(obj, stage):
    """
    Pull database from your deployed website. Stage is either
    test (default) or live
    """
    localdev.ImportRemoteDatabase(client=obj, stage=stage)()


@project_pull.command(name='media')
@click.argument('stage', default='test')
@click.pass_obj
def pull_media(obj, stage):
    """
    Pull media files from your deployed website. Stage is either
    test (default) or live
    """
    localdev.pull_media(obj, stage)


@project.group(name='push')
def project_push():
    """Push db or media files to the Divio Cloud"""
    pass


@project_push.command(name='db')
@click.argument('stage', default='test')
@click.option('--noinput', is_flag=True, default=False, help="Don't ask for confirmation")
@click.pass_obj
def push_db(obj, stage, noinput):
    """
    Push database to your deployed website. Stage is either
    test (default) or live
    """

    if not noinput:
        click.secho(messages.PUSH_DB_WARNING.format(stage=stage), fg='red')
        if not click.confirm('\nAre you sure you want to continue?'):
            return
    localdev.push_db(obj, stage)


@project_push.command(name='media')
@click.argument('stage', default='test')
@click.option('--noinput', is_flag=True, default=False, help="Don't ask for confirmation")
@click.pass_obj
def push_media(obj, stage, noinput):
    """
    Push database to your deployed website. Stage is either
    test (default) or live
    """

    if not noinput:
        click.secho(messages.PUSH_MEDIA_WARNING.format(stage=stage), fg='red')
        if not click.confirm('\nAre you sure you want to continue?'):
            return
    localdev.push_media(obj, stage)


@project.group(name='import')
def project_import():
    """Import local database dump"""
    pass


@project_import.command(name='db')
@click.argument('dump-path', default=localdev.DEFAULT_DUMP_FILENAME, type=click.Path(exists=True))
@click.pass_obj
def import_db(obj, dump_path):
    """
    Load a database dump into your local database
    """
    localdev.ImportLocalDatabase(client=obj, custom_dump_path=dump_path)()


@project.group(name='export')
def project_export():
    """Export local database dump"""
    pass


@project_export.command(name='db')
def export_db():
    """
    Export a dump of your local database
    """
    localdev.export_db()


@project.command(name='develop')
@click.argument('package')
@click.option(
    '--no-rebuild', is_flag=True, default=False,
    help='Do not rebuild docker container automatically'
)
@click.pass_obj
def project_develop(obj, package, no_rebuild):
    """Add a package 'package' to your local project environment"""
    localdev.develop_package(package, no_rebuild)


@cli.group()
@click.option('-p', '--path', default='.', help='Addon directory')
@click.pass_obj
def addon(obj, path):
    """Validate and upload addon packages to the Divio Cloud"""
    pass


@addon.command(name='validate')
@click.pass_context
def addon_validate(ctx):
    """Validate addon configuration"""
    try:
        validate_addon(ctx.parent.params['path'])
    except exceptions.AldrynException as exc:
        raise click.ClickException(*exc.args)
    click.echo('Addon is valid!')


@addon.command(name='upload')
@click.pass_context
def addon_upload(ctx):
    """Upload addon to the Divio Cloud"""
    try:
        ret = upload_addon(ctx.obj, ctx.parent.params['path'])
    except exceptions.AldrynException as exc:
        raise click.ClickException(*exc.args)
    click.echo(ret)


@addon.command(name='register')
@click.argument('verbose_name')
@click.argument('package_name')
@click.option('-o', '--organisation', help='Register for an organisation', type=int)
@click.pass_context
def addon_register(ctx, package_name, verbose_name, organisation):
    """Register your addon on the Divio Cloud\n
    - Verbose Name:        Name of the Addon as it appears in the Marketplace.
    - Package Name:        System wide unique Python package name
    """
    ret = ctx.obj.register_addon(package_name, verbose_name, organisation)
    click.echo(ret)


@cli.group()
@click.option('-p', '--path', default='.', help='Boilerplate directory')
@click.pass_obj
def boilerplate(obj, path):
    """Validate and upload boilerplate packages to the Divio Cloud"""
    pass


@boilerplate.command(name='validate')
@click.pass_context
def boilerplate_validate(ctx):
    """Validate boilerplate configuration"""
    try:
        validate_boilerplate(ctx.parent.params['path'])
    except exceptions.AldrynException as exc:
        raise click.ClickException(*exc.args)
    click.echo('Boilerplate is valid!')


@boilerplate.command(name='upload')
@click.option('--noinput', is_flag=True, default=False, help="Don't ask for confirmation")
@click.pass_context
def boilerplate_upload(ctx, noinput):
    """Upload boilerplate to the Divio Cloud"""
    try:
        ret = upload_boilerplate(ctx.obj, ctx.parent.params['path'], noinput)
    except exceptions.AldrynException as exc:
        raise click.ClickException(*exc.args)
    click.echo(ret)


@cli.group()
def backup():
    """Manage backups for projects hosted on Divio Cloud"""


@backup.command(name='decrypt')
@click.argument('key', type=click.File('rb'))
@click.argument('backup', type=click.File('rb'))
@click.argument('destination', type=click.File('wb'))
def backup_decrypt(key, backup, destination):
    """Decrypt a backup downloaded from Divio Cloud"""
    key = base64.b64decode(key.read(1024).strip())
    decryptor = crypto.StreamDecryptor(key=key)

    for chunk in decryptor(backup):
        destination.write(chunk)


@cli.command()
@click.option(
    '-s', '--skip-check', is_flag=True, default=False,
    help="don't check PyPI for newer version",
)
@click.option(
    '-m', '--machine-readable', is_flag=True, default=False,
)
@click.pass_obj
def version(obj, skip_check, machine_readable):
    """Show version info"""
    if skip_check:
        from . import __version__
        update_info = {'current': __version__}
    else:
        update_info = obj.config.check_for_updates(force=True)

    update_info['location'] = os.path.dirname(os.path.realpath(sys.executable))

    if machine_readable:
        click.echo(json.dumps(update_info))
    else:
        click.echo(
            'divio-cli {} from {}\n'.format(
                update_info['current'],
                update_info['location'],
            )
        )

        if not skip_check:
            if update_info['update_available']:
                click.secho(
                    "New version {version} is available! You can upgrade "
                    "using one of the following:\n\n"
                    " - Use the Divio App to automatically update to the newest version\n"
                    "   https://www.divio.com/app/\n\n"
                    " - Upgrade from PyPI\n"
                    "   pip install --upgrade divio-cli\n\n"
                    " - Download the latest release from GitHub\n"
                    "   https://github.com/divio/divio-cli/releases"
                    .format(version=update_info['remote']),
                    fg='yellow'
                )
            elif update_info['pypi_error']:
                click.secho(
                    'There was an error while trying to check for the latest '
                    'version on pypi.python.org:\n'
                    '{}'.format(update_info['pypi_error']),
                    fg='red',
                )
            else:
                click.echo('You have the latest version of divio-cli!')


@cli.command()
@click.option(
    '-m', '--machine-readable', is_flag=True, default=False,
)
@click.option('-c', '--checks', default=None)
@click.pass_obj
def doctor(obj, machine_readable, checks):
    """Check if your system meets the requirements
    for local development of Divio Cloud projects"""

    if checks:
        checks = checks.split(',')

    if machine_readable:
        errors = {
            check: error
            for check, check_name, error
            in check_requirements(obj.config, checks)
        }
        exitcode = 1 if any(errors.values()) else 0
        click.echo(json.dumps(errors), nl=False)
    else:
        click.echo('Verifying your system setup')
        exitcode = 0 if check_requirements_human(obj.config, checks) else 1

    sys.exit(exitcode)
