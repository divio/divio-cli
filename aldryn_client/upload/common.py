import json
from io import StringIO

from ..utils import tar_add_stringio
from ..validators.common import load_config, get_license


def add_meta_files(tar, path, config_filename):
    # config json file
    config_json = load_config(config_filename, path)
    config_json_fobj = StringIO()
    json.dump(config_json, config_json_fobj)
    tar_add_stringio(tar, config_json_fobj, config_filename)

    # license
    license_filepath = get_license(path)
    if license_filepath:
        tar.add(license_filepath, 'LICENSE.txt')
