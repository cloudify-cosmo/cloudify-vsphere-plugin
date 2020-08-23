from os import path, pardir
from ecosystem_cicd_tools.release import plugin_release_with_latest
from ecosystem_cicd_tools.validations import get_plugin_yaml_version


setup_py = path.join(
    path.abspath(path.join(path.dirname(__file__), pardir)),
    'setup.py')


if __name__ == '__main__':
    plugin_release_with_latest(
        'cloudify-vsphere-plugin', get_plugin_yaml_version(setup_py))
