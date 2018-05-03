#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import setuptools

setuptools.setup(
    zip_safe=True,
    name='cloudify-vsphere-plugin',
    version='2.2.2',
    packages=[
        'vsphere_plugin_common',
        'vsphere_plugin_common.vendored_collections',
        'vsphere_server_plugin',
        'vsphere_network_plugin',
        'vsphere_storage_plugin'
    ],
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=[
        "cloudify-plugins-common>=3.3",
        "pyvmomi==5.5.0.2014.1.1",
        "netaddr==0.7.18",
        "pyyaml==3.10"
    ],
)
