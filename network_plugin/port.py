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

from cloudify import ctx
from cloudify.decorators import operation
from cloudify import exceptions as cfy_exc
import network_plugin
import server_plugin
from vsphere_plugin_common import with_network_client


@operation
@with_network_client
def create(network_client, **kwargs):
    capabilities = ctx.capabilities.get_all().values()

    connected_networks = _get_connected_networks(capabilities)
    if len(connected_networks) != 1:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to create port: port should be '
            'connected to one network')
    connected_servers = _get_connected_servers(capabilities)
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
@with_network_client
def delete(network_client, **kwargs):
    capabilities = ctx.capabilities.get_all().values()
    connected_networks = _get_connected_networks(capabilities)
    connected_servers = _get_connected_servers(capabilities)
    network_name = connected_networks[0][network_plugin.network.NETWORK_NAME]
    switch_distributed = \
        connected_networks[0][network_plugin.network.SWITCH_DISTRIBUTED]
    server_id = connected_servers[0][server_plugin.server.VSPHERE_SERVER_ID]

    network_client.remove_network_interface(server_id, network_name,
                                            switch_distributed)


def _get_connected_networks(context_capabilities):
    return [rt_properties for rt_properties in context_capabilities
            if network_plugin.network.NETWORK_NAME in rt_properties]


def _get_connected_servers(context_capabilities):
    return [rt_properties for rt_properties in context_capabilities
            if server_plugin.server.VSPHERE_SERVER_ID in rt_properties]
