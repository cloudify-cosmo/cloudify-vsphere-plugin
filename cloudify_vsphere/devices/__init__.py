########
# Copyright (c) 2018-2019 Cloudify Platform Ltd. All rights reserved
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
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError
from cloudify_vsphere.utils import find_rels_by_type
from vsphere_plugin_common.constants import (
    VSPHERE_SERVER_ID,
    NETWORK_NAME,
    IP,
    SWITCH_DISTRIBUTED,
    VSPHERE_SERVER_CONNECTED_NICS)
from vsphere_plugin_common import ControllerClient, ServerClient

RELATIONSHIP_NIC_TO_NETWORK = \
    'cloudify.relationships.vsphere.nic_connected_to_network'


def add_connected_network(node_instance, nic_properties=None):
    connected_network = None
    nets_from_rels = find_rels_by_type(
        node_instance, RELATIONSHIP_NIC_TO_NETWORK)
    if len(nets_from_rels) > 1:
        raise NonRecoverableError(
            'Currently only one relationship of type {0} '
            'is supported per node.'.format(
                RELATIONSHIP_NIC_TO_NETWORK))
    elif len(nets_from_rels) < 1:
        return
    net_from_rel = nets_from_rels[0]
    network_name = \
        net_from_rel.target.instance.runtime_properties.get(
            NETWORK_NAME, nic_properties.get('name'))
    switch_distributed = \
        net_from_rel.target.instance.runtime_properties.get(
            SWITCH_DISTRIBUTED)
    if network_name:
        connected_network = {
            'name': network_name,
            'switch_distributed': switch_distributed
        }
    if not connected_network:
        return
    nic_configuration = nic_properties.get('network_configuration')
    if nic_configuration:
        connected_network.update(nic_configuration)
    node_instance.runtime_properties['connected_network'] = \
        connected_network


def controller_without_connected_networks(runtime_properties):
    controller_properties = deepcopy(runtime_properties)

    try:
        del controller_properties['connected_networks']
        del controller_properties['connected']
    except KeyError:
        pass

    return controller_properties


@operation
def create_controller(ctx, **kwargs):
    controller_properties = ctx.instance.runtime_properties
    controller_properties.update(kwargs)
    ctx.logger.info("Properties {0}".format(repr(controller_properties)))
    add_connected_network(ctx.instance, controller_properties)


@operation
def delete_controller(ctx, **kwargs):
    for key in list(ctx.instance.runtime_properties.keys()):
        del ctx.instance.runtime_properties[key]


@operation
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

    scsi_spec, controller_type = cl.generate_scsi_card(
        scsi_properties, hostvm_properties.get(VSPHERE_SERVER_ID))

    ctx.source.instance.runtime_properties.update(cl.attach_controller(
        hostvm_properties.get(VSPHERE_SERVER_ID),
        scsi_spec, controller_type))


@operation
def attach_ethernet_card(ctx, **kwargs):
    if 'busKey' in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.source.instance.runtime_properties['busKey']))
        return
    attachment = _attach_ethernet_card(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        controller_without_connected_networks(
            ctx.source.instance.runtime_properties))
    ctx.source.instance.runtime_properties.update(attachment)


@operation
def attach_server_to_ethernet_card(ctx, **kwargs):
    if 'busKey' in ctx.target.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.target.instance.runtime_properties['busKey']))
        return
    if ctx.target.instance.id not in \
            ctx.source.instance.runtime_properties.get(
                VSPHERE_SERVER_CONNECTED_NICS, []):
        attachment = _attach_ethernet_card(
            ctx.target.node.properties.get("connection_config"),
            ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
            controller_without_connected_networks(
                ctx.target.instance.runtime_properties))
        ctx.target.instance.runtime_properties.update(attachment)
    ip = _get_card_ip(
        ctx.source.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('name'))
    ctx.source.instance.runtime_properties[IP] = ip


@operation
def detach_controller(ctx, **kwargs):
    if 'busKey' not in ctx.source.instance.runtime_properties:
        ctx.logger.info("Contoller dettached.")
        return
    _detach_controller(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.source.instance.runtime_properties.get('busKey'))
    del ctx.source.instance.runtime_properties['busKey']
    controller_without_connected_networks(
            ctx.source.instance.runtime_properties)


@operation
def detach_server_from_controller(ctx, **kwargs):
    if ctx.target.instance.id not in \
            ctx.source.instance.runtime_properties.get(
                VSPHERE_SERVER_CONNECTED_NICS, []):
        if 'busKey' not in ctx.target.instance.runtime_properties:
            ctx.logger.info("Contoller dettached.")
            return
        _detach_controller(
            ctx.target.node.properties.get("connection_config"),
            ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
            ctx.target.instance.runtime_properties.get('busKey'))
        del ctx.target.instance.runtime_properties['busKey']
    ctx.target.instance.runtime_properties = \
        controller_without_connected_networks(
            ctx.target.instance.runtime_properties)


def _attach_ethernet_card(client_config, server_id, ethernet_card_properties):
    cl = ControllerClient()
    cl.get(config=client_config)

    nicspec, controller_type = cl.generate_ethernet_card(
        ethernet_card_properties)
    return cl.attach_controller(server_id, nicspec, controller_type)


def _detach_controller(client_config, server_id, bus_key):
    cl = ControllerClient()
    cl.get(config=client_config)
    cl.detach_controller(server_id, bus_key)


def _get_card_ip(client_config, server_id, nic_name):
    server_client = ServerClient()
    server_client.get(config=client_config)
    vm = server_client.get_server_by_id(server_id)
    return server_client.get_server_ip(vm, nic_name, ignore_local=False)
