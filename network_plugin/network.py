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
                                   transform_resource_name)


@operation
@with_network_client
def create(network_client, **kwargs):
    network = {
        'name': ctx.instance.id,
    }
    network.update(ctx.node.properties['network'])
    transform_resource_name(network, ctx)

    port_group_name = network['name']
    vlan_id = network['vlan_id']
    vswitch_name = network['vswitch_name']
    network_client.create_port_group(port_group_name, vlan_id, vswitch_name)


@operation
@with_network_client
def delete(network_client, **kwargs):
    port_group_name = ctx.node.properties['network'].get('name') or \
        ctx.instance.id
    network_client.delete_port_group(port_group_name)
