#########
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

# Third party imports

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common import with_network_client
from vsphere_plugin_common._compat import unquote
from vsphere_plugin_common.utils import (
    op,
    is_node_deprecated,
    check_name_for_special_characters
)
from vsphere_plugin_common.constants import (
    NETWORK_ID,
    NETWORK_MTU,
    NETWORK_NAME,
    NETWORK_CIDR,
    NETWORK_STATUS,
    SWITCH_DISTRIBUTED,
)


@op
@with_network_client
def create(ctx,
           network_client,
           network,
           use_external_resource):
    is_node_deprecated(ctx.node.type)
    network.update(network)
    network['name'] = get_network_name(ctx, network)
    check_name_for_special_characters(network['name'])
    port_group_name = network['name']
    switch_distributed = network['switch_distributed']

    network_id = _get_network_ids(
        name=port_group_name,
        distributed=switch_distributed,
        client=network_client,
    )

    creating = \
        ctx.instance.runtime_properties.get(NETWORK_STATUS) == 'creating'
    created = \
        ctx.instance.runtime_properties.get(NETWORK_STATUS) == 'created'

    if use_external_resource:
        if not network_id:
            raise NonRecoverableError(
                'Could not use existing {distributed}network "{name}" as no '
                '{distributed}network by that name exists!'.format(
                    name=port_group_name,
                    distributed='distributed ' if switch_distributed else '',
                )
            )
    else:
        if network_id and created:
            ctx.logger.info('Instance is already created.')
        elif network_id and creating and switch_distributed:
            ctx.instance.runtime_properties[NETWORK_STATUS] = 'created'
            ctx.instance.update()
        else:
            if network_id and not creating:
                raise NonRecoverableError(
                    'Could not create new {distributed} network "{name}" as '
                    'a {distributed} network by that name '
                    'already exists.'.format(
                        name=port_group_name,
                        distributed=(
                            'distributed ' if switch_distributed else '')))
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
                                                    vswitch_name,
                                                    instance=ctx.instance)
            else:
                network_client.create_port_group(port_group_name,
                                                 vlan_id,
                                                 vswitch_name,
                                                 instance=ctx.instance)
            ctx.logger.info('Successfully created {type}: {name}'.format(
                            type=get_network_type(network),
                            name=network['name']))
        # update networks id's
        network_id = _get_network_ids(
            name=port_group_name,
            distributed=switch_distributed,
            client=network_client,
            use_cached=False,
        )

    ctx.instance.runtime_properties[NETWORK_ID] = network_id
    ctx.instance.runtime_properties[NETWORK_NAME] = port_group_name
    ctx.instance.runtime_properties[SWITCH_DISTRIBUTED] = switch_distributed
    ctx.instance.update()

    mtu = network_client.get_network_mtu(
        name=port_group_name, switch_distributed=switch_distributed)
    ctx.instance.runtime_properties[NETWORK_MTU] = mtu
    cidr = network_client.get_network_cidr(
        name=port_group_name, switch_distributed=switch_distributed)
    ctx.instance.runtime_properties[NETWORK_CIDR] = cidr
    ctx.instance.update()


@op
@with_network_client
def delete(ctx, network_client, network, use_external_resource):
    port_group_name = get_network_name(ctx, network)
    switch_distributed = network.get('switch_distributed')
    if use_external_resource:
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
            network_client.delete_dv_port_group(port_group_name,
                                                instance=ctx.instance)
        else:
            network_client.delete_port_group(port_group_name)
        ctx.logger.info('Successfully deleted {type}: {name}'.format(
                        type=get_network_type(network),
                        name=network['name']))


def get_network_type(network):
    return ('distributed port group' if network['switch_distributed']
            else 'port group')


def get_network_name(ctx, network):
    if 'name' in network:
        net_name = network['name']
    else:
        net_name = ctx.instance.id
    return net_name


def _get_network_ids(name, distributed, client, use_cached=True):
    name = unquote(name)
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
