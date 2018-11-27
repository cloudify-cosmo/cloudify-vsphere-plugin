########
# Copyright (c) 2018 GigaSpaces Technologies Ltd. All rights reserved
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

from cloudify.decorators import operation
from cloudify.exceptions import OperationRetry
from vsphere_plugin_common.constants import VSPHERE_SERVER_ID
from vsphere_plugin_common import ContollerClient, ServerClient


@operation
def create_contoller(ctx, **kwargs):
    controller_properties = ctx.instance.runtime_properties
    controller_properties.update(kwargs)
    ctx.logger.info("Properties {0}".format(repr(controller_properties)))


@operation
def delete_contoller(ctx, **kwargs):
    for key in list(ctx.instance.runtime_properties.keys()):
        del ctx.instance.runtime_properties[key]


@operation
def attach_scsi_contoller(ctx, **kwargs):
    scsi_properties = ctx.source.instance.runtime_properties
    hostvm_properties = ctx.target.instance.runtime_properties
    ctx.logger.debug("Source {}".format(repr(scsi_properties)))
    ctx.logger.debug("Target {}".format(repr(hostvm_properties)))

    cl = ContollerClient()
    cl.get(config=ctx.source.node.properties.get("connection_config"))

    scsi_spec, controller_type = cl.generate_scsi_card(
        scsi_properties, hostvm_properties.get(VSPHERE_SERVER_ID))

    scsi_properties.update(cl.attach_controller(
        hostvm_properties.get(VSPHERE_SERVER_ID), scsi_spec, controller_type))


@operation
def attach_ethernet_card(ctx, **kwargs):

    max_retries = kwargs.get('max_retries', 10)
    server_id = ctx.source.instance.runtime_properties[VSPHERE_SERVER_ID]
    nic_name = ctx.target.instance.runtime_properties.get('name')
    error_message = 'NIC {0} on Server {1} does not have an IP.'.format(
        nic_name, server_id)

    if ctx.operation.retry_number == 0:
        ctx.logger.debug(
            'Creating NIC on server {0} with these properties: {1}'.format(
                server_id, ctx.source.instance.runtime_properties))
        _attach_card(
            ctx.target.node.properties.get("connection_config"),
            ctx.source.instance.runtime_properties,
            server_id,
        )

    ctx.logger.debug(
        'Attempting to get IP of NIC name {0} on server {1}.'.format(
            nic_name, server_id))

    ip = _get_card_ip(
        ctx.source.node.properties.get("connection_config"),
        server_id,
        nic_name)

    if (not ip or ip == 'null') and \
            ctx.operation.retry_number == max_retries:
        ctx.logger.warn(
            error_message + ' and max retries is {0}'.format(
                max_retries))
        return

    raise OperationRetry(error_message)


@operation
def detach_contoller(ctx, **kwargs):

    server_id = ctx.source.instance.runtime_properties[VSPHERE_SERVER_ID]
    ctx.logger.debug('Removing NIC from server: {0}'.format(server_id))
    _detach_controller(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties,
        server_id)


def _attach_card(controller_client_config, nic_properties, server_id):
    controller_client = ContollerClient()
    controller_client.get(config=controller_client_config)
    nicspec, controller_type = \
        controller_client.generate_ethernet_card(nic_properties)
    nic_properties.update(
        controller_client.attach_controller(
            server_id, nicspec, controller_type))


def _get_card_ip(server_client_config, server_id, nic_name):
    server_client = ServerClient()
    server_client.get(config=server_client_config)
    vm = server_client.get_server_by_id(server_id)
    return server_client.get_server_ip(vm, nic_name, ignore_local=False)


def _detach_controller(connection_config,
                       controller_properties,
                       server_id):

    cl = ContollerClient()
    cl.get(connection_config)
    cl.detach_contoller(server_id, controller_properties.get('busKey'))
    del controller_properties['busKey']
