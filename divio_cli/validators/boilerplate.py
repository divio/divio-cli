from .. import settings
from .common import load_config, validate_package_config


BOILERPLATE_REQUIRED_CONFIG_KEYS = (
    "package-name",
    "identifier",
    "version",
    "templates",
)


def validate_boilerplate_config(config, path):
    errors = []

    errors += validate_package_config(
        config=config,
        required_keys=BOILERPLATE_REQUIRED_CONFIG_KEYS,
        path=path,
    )

    templates = config.get("templates", [])
    if isinstance(templates, (list, tuple)):
        for template in templates:
            if not isinstance(template, (list, tuple)) or len(template) != 2:
                errors.append(
                    "Templates must be a list/tuple of lists/tuples "
                    "with two items each."
                )

    excluded_files = config.get("excluded", [])
    if not isinstance(excluded_files, (list, tuple)):
        errors.append("Included files setting must be a list or a tuple.")

    if config.get("protected"):
        errors.append(
            "The `protected` section is deprecated and not used "
            "anymore. By default, all files will be included in "
            "the boilerplate. If you wish to exclude some files, "
            "use the `excluded` section."
        )

    return errors


def validate_boilerplate(path=None):
    config = load_config(settings.BOILERPLATE_CONFIG_FILENAME, path)
    return validate_boilerplate_config(config, path)
