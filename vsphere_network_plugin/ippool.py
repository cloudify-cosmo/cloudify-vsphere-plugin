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
from cloudify.exceptions import NonRecoverableError

# This package imports
import json
from pyVmomi import VmomiSupport
from vsphere_plugin_common import with_network_client
from vsphere_plugin_common.constants import IPPOOL_ID
from vsphere_plugin_common.utils import (
    op,
    is_node_deprecated,
    find_instances_by_type_from_rels)
from vsphere_plugin_common.utils import check_drift as utils_check_drift


@op
@with_network_client
def create(ctx, network_client, ippool, datacenter_name, **_):
    is_node_deprecated(ctx.node.type)
    if ctx.instance.runtime_properties.get(IPPOOL_ID):
        ctx.logger.info('Instance is already created.')
        return
    networks = find_instances_by_type_from_rels(
        ctx.instance,
        "cloudify.relationships.vsphere.ippool_connected_to_network",
        "cloudify.nodes.vsphere.Network"
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


@op
@with_network_client
def poststart(ctx, network_client, datacenter_name, **_):
    ippool_id = ctx.instance.runtime_properties.get(IPPOOL_ID)
    if not ippool_id:
        raise NonRecoverableError(
            "There is no ippool id.")
    pool = network_client.query_ippool(datacenter_name, ippool_id)
    config = json.loads(json.dumps(pool,
                                   cls=VmomiSupport.VmomiJSONEncoder,
                                   sort_keys=True, indent=4))
    ctx.instance.runtime_properties["expected_configuration"] = config


@op
@with_network_client
def check_drift(ctx, network_client, datacenter_name, **_):
    ippool_id = ctx.instance.runtime_properties.get(IPPOOL_ID)
    if not ippool_id:
        raise NonRecoverableError(
            "There is no ippool id.")
    pool = network_client.query_ippool(datacenter_name, ippool_id)
    current_configuration = json.loads(json.dumps(pool,
                                       cls=VmomiSupport.VmomiJSONEncoder,
                                       sort_keys=True, indent=4))
    expected_configuration = ctx.instance.runtime_properties[
        "expected_configuration"]

    utils_check_drift(ctx.logger,
                      expected_configuration,
                      current_configuration)
