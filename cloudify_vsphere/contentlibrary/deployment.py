# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
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

# Cloudify imports

# This package imports
from cloudify_vsphere.utils import op
from cloudify_vsphere.contentlibrary import ContentLibrary
from vsphere_plugin_common import (
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    CONTENT_ITEM_ID,
    CONTENT_LIBRARY_ID,
    CONTENT_LIBRARY_PROPERTIES,
    VSPHERE_SERVER_ID,
)


@op
def create(ctx, connection_config, library_name, template_name, target,
           deployment_spec):
    runtime_properties = ctx.instance.runtime_properties
    content = ContentLibrary(connection_config)
    library = content.content_library_get(library_name)
    content_library_id = library["id"]
    runtime_properties[CONTENT_LIBRARY_ID] = content_library_id

    item = content.content_item_get(content_library_id, template_name)
    content_item_id = item["id"]
    runtime_properties[CONTENT_ITEM_ID] = content_item_id

    if "name" not in deployment_spec:
        deployment_spec['name'] = ctx.instance.id

    if '_' in deployment_spec['name']:
        orig = deployment_spec['name']
        deployment_spec['name'] = deployment_spec['name'].replace('_', '-')
        ctx.logger.warn(
            'Changing all _ to - in VM name. Name changed from {orig} to '
            '{new}.'.format(
                orig=orig,
                new=deployment_spec['name'],
            )
        )

    deployment = content.content_item_deploy(content_item_id, target,
                                             deployment_spec)
    ctx.logger.debug("Deployed VM id: {vm_id}"
                     .format(vm_id=deployment['resource_id']['id']))
    ctx.instance.runtime_properties[
        VSPHERE_SERVER_ID] = deployment['resource_id']['id']
    ctx.instance.runtime_properties['vm_name'] = deployment_spec['name']


@op
def delete(ctx):
    remove_runtime_properties(CONTENT_LIBRARY_PROPERTIES, ctx)