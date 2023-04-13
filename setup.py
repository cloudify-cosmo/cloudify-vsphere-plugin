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
import pathlib
from setuptools import setup


def get_version():
    current_dir = pathlib.Path(__file__).parent.resolve()

    with open(os.path.join(current_dir, 'cloudify_vsphere/__version__.py'),
              'r') as outfile:
        var = outfile.read()
        return re.search(r'\d+.\d+.\d+', var).group()


setup(
    zip_safe=True,
    name='cloudify-vsphere-plugin',
    version=get_version(),
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
    ],
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=[
        "cloudify-common>=4.5",
        "pyvmomi>=6.7.3,<8.0.0",
        "netaddr>=0.7.19",
        "networkx==1.9.1",
        "cloudify-utilities-plugins-sdk>=0.0.61",
        "requests",
        'deepdiff==3.3.0'
    ]
)
