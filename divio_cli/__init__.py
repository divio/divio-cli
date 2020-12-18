import click

def get_version():
    from importlib_metadata import version, PackageNotFoundError
    try:
        return version("divio-cli")
    except PackageNotFoundError:
        # This should normally not be reached
        click.secho("Can not retrieve the currently installed version of the divio cli. Falling back to `0.0.0`", fg="red")
        return "0.0.0"
