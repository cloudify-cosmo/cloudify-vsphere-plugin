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
    version='1.2',
    packages=[
        'vsphere_plugin_common',
        'server_plugin',
        'network_plugin',
        'storage_plugin'
    ],
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=[
        "cloudify-plugins-common==3.2",
        "pyvmomi",
        "netaddr",
        "pyyaml==3.10"
    ],
)
