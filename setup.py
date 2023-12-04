# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import sys
import pathlib
from setuptools import setup, find_packages


def get_version():
    current_dir = pathlib.Path(__file__).parent.resolve()

    with open(os.path.join(current_dir, 'cloudify_vsphere/__version__.py'),
              'r') as outfile:
        var = outfile.read()
        return re.search(r'\d+.\d+.\d+', var).group()


install_requires = [
        'pyvmomi>=6.7.3,<8.0.0',
        'netaddr>=0.7.19',
        'cloudify-utilities-plugins-sdk',
        'requests',
]

if sys.version_info.major == 3 and sys.version_info.minor == 6:
    packages=[
        'vsphere_plugin_common',
        'vsphere_plugin_common.clients',
        'vsphere_server_plugin',
        'vsphere_network_plugin',
        'vsphere_storage_plugin',
        'cloudify_vsphere',
        'cloudify_vsphere.cluster',
        'cloudify_vsphere.contentlibrary',
        'cloudify_vsphere.datacenter',
        'cloudify_vsphere.datastore',
        'cloudify_vsphere.devices',
        'cloudify_vsphere.hypervisor_host',
        'cloudify_vsphere.resource_pool',
        'cloudify_vsphere.vm_folder',
        'cloudify_vsphere.ovf',
    ]
    install_requires += [
        'cloudify-common>=4.5,<7.0',
        'deepdiff==3.3.0',
    ]
else:
    packages = find_packages()
    install_requires += [
        'fusion-common',
        'deepdiff==5.7.0',
    ]


setup(
    zip_safe=True,
    name='cloudify-vsphere-plugin',
    version=get_version(),
    packages=packages,
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=install_requires
)
