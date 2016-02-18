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
                                   remove_runtime_properties)
from vsphere_plugin_common.constants import(
    NETWORK_NAME,
    SWITCH_DISTRIBUTED,
    NETWORK_RUNTIME_PROPERTIES,
)


@operation
@with_network_client
def create(network_client, **kwargs):
    network = {}
    network.update(ctx.node.properties['network'])
    network['name'] = get_network_name(network)
    network_type = ('distributed port group' if network['switch_distributed']
                    else 'port group')
    ctx.logger.info('Creating new {type} with name \'{name}\' on VLAN {vlan} '
                    'attached to vSwitch: {vswitch}'
                    .format(name=network['name'],
                            type=network_type,
                            vlan=network['vlan_id'],
                            vswitch=network['vswitch_name']))

    port_group_name = network['name']
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
    port_group_name = get_network_name(ctx.node.properties['network'])
    switch_distributed = ctx.node.properties[
        'network'].get('switch_distributed')

    if switch_distributed:
        network_client.delete_dv_port_group(port_group_name)
    else:
        network_client.delete_port_group(port_group_name)
    remove_runtime_properties(NETWORK_RUNTIME_PROPERTIES, ctx)


def get_network_name(network):
    if 'name' in network:
        net_name = network['name']
    else:
        net_name = ctx.instance.id
    return net_name
