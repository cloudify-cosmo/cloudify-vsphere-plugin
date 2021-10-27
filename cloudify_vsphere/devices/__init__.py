########
# Copyright (c) 2018-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from copy import deepcopy

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from vsphere_plugin_common.utils import find_rels_by_type
from vsphere_plugin_common.clients.server import ServerClient
from vsphere_plugin_common.clients.network import ControllerClient
from vsphere_plugin_common import (
    run_deferred_task,
    remove_runtime_properties)
from vsphere_plugin_common.constants import (
    IP,
    NETWORK_NAME,
    VSPHERE_SERVER_ID,
    SWITCH_DISTRIBUTED,
    VSPHERE_SERVER_CONNECTED_NICS)

RELATIONSHIP_NIC_TO_NETWORK = \
    'cloudify.relationships.vsphere.nic_connected_to_network'


def add_connected_network(node_instance, nic_properties=None):
    nets_from_rels = find_rels_by_type(
        node_instance, RELATIONSHIP_NIC_TO_NETWORK)
    if len(nets_from_rels) > 1:
        raise NonRecoverableError(
            'Currently only one relationship of type {0} '
            'is supported per node.'.format(RELATIONSHIP_NIC_TO_NETWORK))
    elif len(nets_from_rels) < 1:
        ctx.logger.debug('No NIC to network relationships found.')
        return
    net_from_rel = nets_from_rels[0]
    network_name = \
        net_from_rel.target.instance.runtime_properties.get(
            NETWORK_NAME, nic_properties.get('name'))
    if network_name:
        connected_network = {
            'name': network_name,
            'switch_distributed':
            net_from_rel.target.instance.runtime_properties.get(
                SWITCH_DISTRIBUTED)
        }
    else:
        ctx.logger.error('The target network does not have an ID.')
        return
    nic_configuration = nic_properties.get('network_configuration')
    if nic_configuration:
        connected_network.update(nic_configuration)
    node_instance.runtime_properties['connected_network'] = connected_network


def controller_without_connected_networks(runtime_properties):
    controller_properties = deepcopy(runtime_properties)

    try:
        del controller_properties['connected_networks']
        del controller_properties['connected']
    except KeyError:
        pass

    return controller_properties


@operation(resumable=True)
def create_controller(ctx, **kwargs):
    controller_properties = ctx.instance.runtime_properties
    controller_properties.update(kwargs)
    ctx.logger.info("Properties {0}".format(repr(controller_properties)))
    add_connected_network(ctx.instance, controller_properties)


@operation(resumable=True)
def delete_controller(**kwargs):
    remove_runtime_properties()


@operation(resumable=True)
def attach_scsi_controller(ctx, **kwargs):
    if 'busKey' in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.source.instance.runtime_properties['busKey']))
        return
    scsi_properties = controller_without_connected_networks(
        ctx.source.instance.runtime_properties)
    hostvm_properties = ctx.target.instance.runtime_properties
    ctx.logger.debug("Source {0}".format(repr(scsi_properties)))
    ctx.logger.debug("Target {0}".format(repr(hostvm_properties)))

    cl = ControllerClient()
    cl.get(config=ctx.source.node.properties.get("connection_config"))

    run_deferred_task(cl, ctx.source.instance)

    scsi_spec, controller_type = cl.generate_scsi_card(
        scsi_properties, hostvm_properties.get(VSPHERE_SERVER_ID))

    controller_settings = cl.attach_controller(
        hostvm_properties.get(VSPHERE_SERVER_ID),
        scsi_spec, controller_type,
        instance=ctx.source.instance)

    ctx.logger.info("Controller attached with {buskey} key.".format(
        buskey=controller_settings['busKey']))

    ctx.source.instance.runtime_properties.update(controller_settings)
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def attach_ethernet_card(ctx, **kwargs):
    if 'busKey' in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.source.instance.runtime_properties['busKey']))
        return
    attachment = _attach_ethernet_card(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        controller_without_connected_networks(
            ctx.source.instance.runtime_properties),
        instance=ctx.target.instance)
    ctx.source.instance.runtime_properties.update(attachment)
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def attach_server_to_ethernet_card(ctx, **kwargs):
    ctx.logger.info("***** attach_server_to_ethernet_card")
    ctx.logger.info("*****1 ctx.target.instance.runtime_properties: {}"
                    .format(ctx.target.instance.runtime_properties))
    ctx.logger.info("*****2 ctx.source.instance.runtime_properties: {}"
                    .format(ctx.source.instance.runtime_properties))

    if 'busKey' in ctx.target.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.target.instance.runtime_properties['busKey']))
        return
    if ctx.target.instance.id in ctx.source.instance.runtime_properties.get(
            VSPHERE_SERVER_CONNECTED_NICS, []):
        ctx.logger.info("**** go to do - _detach_controller")
        _detach_controller(
            ctx.target.node.properties.get("connection_config"),
            ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
            controller_without_connected_networks(
                ctx.target.instance.runtime_properties),
            instance=ctx.target.instance)

    ctx.logger.info("**** go to do - _attach_ethernet_card")
    attachment = _attach_ethernet_card(
        ctx.target.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        controller_without_connected_networks(
            ctx.target.instance.runtime_properties),
        instance=ctx.target.instance)

    ctx.target.instance.runtime_properties.update(attachment)
    ctx.target.instance.runtime_properties.dirty = True
    ctx.target.instance.update()
    ip = _get_card_ip(
        ctx.source.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('name'))
    ctx.source.instance.runtime_properties[IP] = ip
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def detach_controller(ctx, **kwargs):
    if 'busKey' not in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller was not attached, skipping.")
        return
    _detach_controller(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.source.instance.runtime_properties.get('busKey'),
        instance=ctx.source.instance)
    del ctx.source.instance.runtime_properties['busKey']


@operation(resumable=True)
def detach_server_from_controller(ctx, **kwargs):
    if ctx.target.instance.id in \
            ctx.source.instance.runtime_properties.get(
                VSPHERE_SERVER_CONNECTED_NICS, []):
        return
    if 'busKey' not in ctx.target.instance.runtime_properties:
        ctx.logger.info("Controller was not attached, skipping.")
        return
    _detach_controller(
        ctx.target.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('busKey'),
        instance=ctx.target.instance)
    del ctx.target.instance.runtime_properties['busKey']


def _attach_ethernet_card(client_config,
                          server_id,
                          ethernet_card_properties,
                          instance):
    cl = ControllerClient()
    cl.get(config=client_config)
    run_deferred_task(cl, instance)
    nicspec, controller_type = cl.generate_ethernet_card(
        ethernet_card_properties)
    return cl.attach_controller(server_id, nicspec, controller_type,
                                instance=instance)


def _detach_controller(client_config, server_id, bus_key, instance):
    cl = ControllerClient()
    cl.get(config=client_config)
    run_deferred_task(cl, instance)
    ctx.logger.info("** in _detach_controller ")
    ctx.logger.info("** server_id:{} ".format(server_id))
    ctx.logger.info("** bus_key:{} ".format(bus_key))
    ctx.logger.info("**  ctx.target.instance.runtime_properties:{} "
                    .format(ctx.target.instance.runtime_properties))
    cl.detach_controller(server_id, bus_key, instance)


def _get_card_ip(client_config, server_id, nic_name):
    server_client = ServerClient()
    server_client.get(config=client_config)
    vm = server_client.get_server_by_id(server_id)
    return server_client.get_server_ip(vm, nic_name, ignore_local=False)
