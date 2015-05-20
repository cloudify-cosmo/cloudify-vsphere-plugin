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

import cloudify
import network_plugin
import server_plugin
import vsphere_plugin_common as vpc

from cloudify import decorators
from cloudify import exceptions as cfy_exc

ctx = cloudify.ctx
operation = decorators.operation


@operation
@vpc.with_network_client
def create(network_client, **kwargs):
    connected_networks = _get_connected_networks()
    if len(connected_networks) != 1:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to create port: port should be '
            'connected to one network')
    connected_servers = _get_connected_servers()
    if len(connected_servers) != 1:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to create port: port should be '
            'connected to one server')

    network_name = connected_networks[0][network_plugin.network.NETWORK_NAME]
    switch_distributed = \
        connected_networks[0][network_plugin.network.SWITCH_DISTRIBUTED]
    server_id = connected_servers[0][server_plugin.server.VSPHERE_SERVER_ID]
    mac_address = ctx.node.properties.get('mac')

    network_client.add_network_interface(server_id, network_name,
                                         switch_distributed, mac_address)


@operation
@vpc.with_network_client
def delete(network_client, **kwargs):
    connected_networks = _get_connected_networks()
    connected_servers = _get_connected_servers()
    network_name = connected_networks[0][network_plugin.network.NETWORK_NAME]
    switch_distributed = \
        connected_networks[0][network_plugin.network.SWITCH_DISTRIBUTED]
    server_id = connected_servers[0][server_plugin.server.VSPHERE_SERVER_ID]

    network_client.remove_network_interface(server_id, network_name,
                                            switch_distributed)


def _get_connected_networks():
    return [relationship.target.instance.runtime_properties
            for relationship in ctx.instance.relationships
            if network_plugin.network.NETWORK_NAME
            in relationship.target.instance.runtime_properties]


def _get_connected_servers():
    return [relationship.target.instance.runtime_properties
            for relationship in ctx.instance.relationships
            if server_plugin.server.VSPHERE_SERVER_ID
            in relationship.target.instance.runtime_properties]
