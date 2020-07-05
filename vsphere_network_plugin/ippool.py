# Copyright (c) 2016-2020 Cloudify Platform Ltd. All rights reserved
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

# Cloudify imports

# This package imports
from vsphere_plugin_common import with_network_client
from vsphere_plugin_common.constants import IPPOOL_ID
from vsphere_plugin_common.utils import (
    op,
    find_instances_by_type_from_rels)


@op
@with_network_client
def create(ctx, network_client, ippool, datacenter_name, **_):
    if ctx.instance.runtime_properties.get(IPPOOL_ID):
        ctx.logger.info('Instance is already created.')
        return
    networks = find_instances_by_type_from_rels(
        ctx.instance,
        "cloudify.relationships.vsphere.ippool_connected_to_network",
        "cloudify.vsphere.nodes.Network"
    )
    ctx.instance.runtime_properties[IPPOOL_ID] = network_client.create_ippool(
        datacenter_name, ippool, networks)


@op
@with_network_client
def delete(ctx, network_client, datacenter_name, **_):
    ippool = ctx.instance.runtime_properties.get(IPPOOL_ID)
    if not ippool:
        return
    network_client.delete_ippool(
        datacenter_name, ctx.instance.runtime_properties[IPPOOL_ID])
