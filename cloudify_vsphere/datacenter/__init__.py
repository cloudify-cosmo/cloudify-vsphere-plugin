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
# Stdlib imports

# Third party imports
from pyVmomi import vim

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common.utils import op
from vsphere_plugin_common import with_server_client
from vsphere_plugin_common.constants import DATACENTER_ID


@op
@with_server_client
def create(ctx, server_client, name, use_external_resource):

    if ctx.node.type in "cloudify.vsphere.nodes.Datacenter":
        ctx.logger.error('The node {} is deprecated, '
            'please update your node type.'.format(ctx.node.type))

    wmware_resource = server_client._get_obj_by_name(
        vim.Datacenter,
        name,
    )

    if use_external_resource:
        if not wmware_resource:
            raise NonRecoverableError(
                'Could not use existing datacenter "{name}" as no '
                'datacenter by that name exists!'.format(
                    name=name,
                )
            )
    else:
        raise NonRecoverableError(
            'Datacenters cannot currently be created by this plugin.'
        )

    ctx.instance.runtime_properties[DATACENTER_ID] = wmware_resource.id


@op
@with_server_client
def delete(ctx, name, use_external_resource, **_):
    if use_external_resource:
        ctx.logger.info(
            'Not deleting existing datacenter: {name}'.format(
                name=name,
            )
        )
    else:
        ctx.logger.info(
            'Not deleting datacenter {name} as creation and deletion of '
            'datacenters is not currently supported by this plugin.'.format(
                name=name,
            )
        )
