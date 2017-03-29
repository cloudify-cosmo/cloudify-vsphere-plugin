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

# Stdlib imports
import urllib

# Third party imports

# Cloudify imports
from cloudify import ctx
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common import (
    with_network_client,
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    NETWORK_ID,
    NETWORK_NAME,
    SWITCH_DISTRIBUTED,
    NETWORK_RUNTIME_PROPERTIES,
)
from cloudify_vsphere.utils.feedback import check_name_for_special_characters


@operation
@with_network_client
def create(network_client, **kwargs):
    network = {}
    network.update(ctx.node.properties['network'])
    network['name'] = get_network_name(network)
    check_name_for_special_characters(network['name'])
    port_group_name = network['name']
    switch_distributed = network['switch_distributed']

    existing_id = _get_network_ids(
        name=port_group_name,
        distributed=switch_distributed,
        client=network_client,
    )

    runtime_properties = ctx.instance.runtime_properties

    creating = runtime_properties.get('status', None) == 'creating'

    if ctx.node.properties.get('use_existing_resource', False):
        if not existing_id:
            raise NonRecoverableError(
                'Could not use existing {distributed}network "{name}" as no '
                '{distributed}network by that name exists!'.format(
                    name=port_group_name,
                    distributed='distributed ' if switch_distributed else '',
                )
            )
        network_id = existing_id
    else:
        if existing_id and not creating:
            raise NonRecoverableError(
                'Could not create new {distributed}network "{name}" as a '
                '{distributed}network by that name already exists!'.format(
                    name=port_group_name,
                    distributed='distributed ' if switch_distributed else '',
                )
            )
        vlan_id = network['vlan_id']
        vswitch_name = network['vswitch_name']

        ctx.logger.info(
            'Creating {type} called {name} and VLAN {vlan} on '
            '{vswitch}'.format(
                type=get_network_type(network),
                name=network['name'],
                vlan=network['vlan_id'],
                vswitch=network['vswitch_name'],
            )
        )
        if switch_distributed:
            network_client.create_dv_port_group(port_group_name,
                                                vlan_id,
                                                vswitch_name)
        else:
            network_client.create_port_group(port_group_name,
                                             vlan_id,
                                             vswitch_name)
        ctx.logger.info('Successfully created {type}: {name}'.format(
                        type=get_network_type(network),
                        name=network['name']))
        network_id = _get_network_ids(
            name=port_group_name,
            distributed=switch_distributed,
            client=network_client,
            use_cached=False,
        )

    runtime_properties[NETWORK_ID] = network_id
    ctx.instance.runtime_properties[NETWORK_NAME] = port_group_name
    ctx.instance.runtime_properties[SWITCH_DISTRIBUTED] = switch_distributed


@operation
@with_network_client
def delete(network_client, **kwargs):
    network = ctx.node.properties['network']
    port_group_name = get_network_name(network)
    switch_distributed = network.get('switch_distributed')
    if ctx.node.properties.get('use_existing_resource', False):
        ctx.logger.info(
            'Not deleting existing {type}: {name}'.format(
                type=get_network_type(network),
                name=network['name'],
            )
        )
    else:
        ctx.logger.info('Deleting {type}: {name}'.format(
                        type=get_network_type(network),
                        name=network['name']))
        if switch_distributed:
            network_client.delete_dv_port_group(port_group_name)
        else:
            network_client.delete_port_group(port_group_name)
        ctx.logger.info('Successfully deleted {type}: {name}'.format(
                        type=get_network_type(network),
                        name=network['name']))
    remove_runtime_properties(NETWORK_RUNTIME_PROPERTIES, ctx)


def get_network_type(network):
    return ('distributed port group' if network['switch_distributed']
            else 'port group')


def get_network_name(network):
    if 'name' in network:
        net_name = network['name']
    else:
        net_name = ctx.instance.id
    return net_name


def _get_network_ids(name, distributed, client, use_cached=True):
    name = urllib.unquote(name)
    if distributed:
        networks = client._get_dv_networks(use_cached)
        networks = [
            network for network in networks if network.name == name
        ]
        if len(networks) > 1:
            # We shouldn't be able to get here
            raise NonRecoverableError(
                'Unexpectedly found multiple distributed networks with name '
                '{name}.'.format(name=name)
            )
        elif len(networks) == 1:
            network_id = networks[0].id
        else:
            network_id = None
    else:
        networks = client._get_standard_networks(use_cached)
        network_id = [
            network.id for network in networks
            if network.name == name
        ]
    return network_id
