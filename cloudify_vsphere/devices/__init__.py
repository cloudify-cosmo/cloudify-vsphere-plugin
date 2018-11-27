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

from vsphere_plugin_common.constants import VSPHERE_SERVER_ID
from vsphere_plugin_common import ContollerClient


@operation
def create_contoller(ctx, **kwargs):
    controller_properties = ctx.instance.runtime_properties
    controller_properties.update(kwargs)
    ctx.logger.info("Properties {}".format(repr(controller_properties)))


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
    attachment = _attach_ethernet_card(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.source.instance.runtime_properties)
    ctx.source.instance.runtime_properties.update(attachment)


@operation
def attach_server_to_ethernet_card(ctx, **kwargs):
    attachment = _attach_ethernet_card(
        ctx.target.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties)
    ctx.target.instance.runtime_properties.update(attachment)


@operation
def detach_contoller(ctx, **kwargs):
    _detach_controller(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.source.instance.runtime_properties.get('busKey'))
    del ctx.source.instance.runtime_properties['busKey']


@operation
def detach_server_from_contoller(ctx, **kwargs):
    _detach_controller(
        ctx.target.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('busKey'))
    del ctx.target.instance.runtime_properties['busKey']


def _attach_ethernet_card(client_config, server_id, ethernet_card_properties):
    cl = ContollerClient()
    cl.get(config=client_config)

    nicspec, controller_type = cl.generate_ethernet_card(
        ethernet_card_properties)
    return cl.attach_controller(server_id, nicspec, controller_type)


def _detach_controller(client_config, server_id, bus_key):
    cl = ContollerClient()
    cl.get(config=client_config)
    cl.detach_contoller(server_id, bus_key)
