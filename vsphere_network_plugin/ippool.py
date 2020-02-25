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
from cloudify_vsphere.utils import op
from vsphere_plugin_common import (
    with_network_client,
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import IPPOOL_ID


@op
@with_network_client
def create(ctx, network_client, ippool, datacenter_name, **kwargs):
    if ctx.instance.runtime_properties.get(IPPOOL_ID):
        ctx.logger.info('Instance is already created.')
        return

    rels = [rel for rel in ctx.instance.relationships if
            "cloudify.relationships.vsphere.ippool_connected_to_network" in
            rel.type_hierarchy]
    networks = [rel.target.instance for rel in rels if
                "cloudify.vsphere.nodes.Network" in
                rel.target.node.type_hierarchy]
    ctx.instance.runtime_properties[IPPOOL_ID] = network_client.create_ippool(
        datacenter_name, ippool, networks)


@op
@with_network_client
def delete(ctx, network_client, datacenter_name, **kwargs):
    ippool = ctx.instance.runtime_properties.get(IPPOOL_ID)
    if not ippool:
        return
    network_client.delete_ippool(
        datacenter_name, ctx.instance.runtime_properties[IPPOOL_ID])
    remove_runtime_properties(ctx)
