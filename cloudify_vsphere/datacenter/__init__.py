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

# Third party imports
from pyVmomi import vim

# Cloudify imports
from cloudify import ctx
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common import (
    with_server_client,
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    DATACENTER_ID,
    DATACENTER_RUNTIME_PROPERTIES,
)


@operation
@with_server_client
def create(server_client, **kwargs):
    use_existing = ctx.node.properties.get('use_existing_resource', False)
    datacenter_name = ctx.node.properties['name']

    existing_id = server_client._get_obj_by_name(
        vim.Datacenter,
        datacenter_name,
    )
    if existing_id is not None:
        existing_id = existing_id.id

    runtime_properties = ctx.instance.runtime_properties

    if use_existing:
        if not existing_id:
            raise NonRecoverableError(
                'Could not use existing datacenter "{name}" as no '
                'datacenter by that name exists!'.format(
                    name=datacenter_name,
                )
            )
        datacenter_id = existing_id
    else:
        raise NonRecoverableError(
            'Datacenters cannot currently be created by this plugin.'
        )

    runtime_properties[DATACENTER_ID] = datacenter_id


@operation
@with_server_client
def delete(server_client, **kwargs):
    use_existing = ctx.node.properties.get('use_existing_resource', False)
    datacenter_name = ctx.node.properties['name']

    if use_existing:
        ctx.logger.info(
            'Not deleting existing datacenter: {name}'.format(
                name=datacenter_name,
            )
        )
    else:
        ctx.logger.info(
            'Not deleting datacenter {name} as creation and deletion of '
            'datacenters is not currently supported by this plugin.'.format(
                name=datacenter_name,
            )
        )
    remove_runtime_properties(DATACENTER_RUNTIME_PROPERTIES, ctx)
