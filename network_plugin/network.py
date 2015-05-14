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
from vsphere_plugin_common import (with_network_client,
                                   transform_resource_name,
                                   remove_runtime_properties)

NETWORK_NAME = 'network_name'
SWITCH_DISTRIBUTED = 'switch_distributed'
NETWORK_RUNTIME_PROPERTIES = [NETWORK_NAME, SWITCH_DISTRIBUTED]


@operation
@with_network_client
def create(network_client, **kwargs):
    network = {
        'name': ctx.instance.id,
    }
    network.update(ctx.node.properties['network'])
    transform_resource_name(network, ctx)

    port_group_name = ctx.instance.id
    vlan_id = network['vlan_id']
    vswitch_name = network['vswitch_name']
    switch_distributed = network['switch_distributed']

    if switch_distributed:
        network_client.create_dv_port_group(port_group_name,
                                            vlan_id,
                                            vswitch_name)
    else:
        network_client.create_port_group(port_group_name,
                                         vlan_id,
                                         vswitch_name)
    ctx.instance.runtime_properties[NETWORK_NAME] = port_group_name
    ctx.instance.runtime_properties[SWITCH_DISTRIBUTED] = switch_distributed


@operation
@with_network_client
def delete(network_client, **kwargs):
    port_group_name = ctx.node.properties['network'].get(
        'name') or ctx.instance.id
    switch_distributed = ctx.node.properties[
        'network'].get('switch_distributed')

    if switch_distributed:
        network_client.delete_dv_port_group(port_group_name)
    else:
        network_client.delete_port_group(port_group_name)
    remove_runtime_properties(NETWORK_RUNTIME_PROPERTIES, ctx)
