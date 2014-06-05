__author__ = 'Oleksandr_Raskosov'

from setuptools import setup

PLUGINS_COMMON_VERSION = '3.0'
PLUGINS_COMMON_BRANCH = "develop"
PLUGINS_COMMON = 'https://github.com/cloudify-cosmo/cloudify-plugins-common' \
    '/tarball/{0}'.format(PLUGINS_COMMON_BRANCH)


setup(
    zip_safe=True,
    name='cloudify-vsphere-plugin',
    version='0.1.0',
    author='Oleksandr_Raskosov',
    author_email='Oleksandr_Raskosov@epam.com',
    packages=[
        'vsphere_plugin_common',
        'server_plugin',
        'network_plugin'
    ],
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=[
        "cloudify-plugins-common",
        "pyvmomi",
        "atexit",
        "time"
    ],
    test_requires=[
        "nose"
    ],
    dependency_links=["{0}#egg=cloudify-plugins-common-{1}"
                      .format(PLUGINS_COMMON, PLUGINS_COMMON_VERSION)]
)
