try:
    from divio_cli.version import __version__
except ModuleNotFoundError:
    from setuptools_scm import get_version

    __version__ = get_version(root=".", relative_to=__file__)
