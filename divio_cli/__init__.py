import click

from divio_cli.domain_models.app_template import AppTemplate  # NOQA


try:
    from .version import version as __version__
except ImportError:
    try:
        from setuptools_scm import get_version

        __version__ = get_version()
    except Exception:
        click.secho(
            "Found no way to get the current version. Falling back to 0.0.0.",
            fg="yellow",
            err=True,
        )
        __version__ = "0.0.0"
