########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import tempfile
import json

import fabric
from fabric.context_managers import settings as fabric_ctx_managers_settings

from cloudify import ctx

from cloudify_cli.bootstrap.tasks import PUBLIC_IP_RUNTIME_PROPERTY

import server_plugin.server as vsphere_server
import vsphere_plugin_common


def configure(vsphere_config):

    manager_public_ip = _get_public_ip()
    _copy_vsphere_configuration_to_manager(manager_public_ip, vsphere_config)


def _get_public_ip():
    server_runtime_props = [v for k, v
                            in ctx.capabilities.get_all().iteritems()
                            if k.startswith('manager_server')][0]
    manager_public_ip = server_runtime_props[vsphere_server.PUBLIC_IP]
    ctx.instance.runtime_properties[PUBLIC_IP_RUNTIME_PROPERTY] = \
        manager_public_ip
    return manager_public_ip


def _copy_vsphere_configuration_to_manager(manager_public_ip,
                                           vsphere_config):
    tmp = tempfile.mktemp()
    with open(tmp, 'w') as f:
        json.dump(vsphere_config, f)
    with fabric_ctx_managers_settings(host_string=manager_public_ip):
        fabric.api.put(
            tmp,
            vsphere_plugin_common.Config.CONNECTION_CONFIG_PATH_DEFAULT)
