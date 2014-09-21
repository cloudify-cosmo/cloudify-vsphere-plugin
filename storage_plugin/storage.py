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


__author__ = 'Oleksandr_Raskosov'


from cloudify.decorators import operation
from vsphere_plugin_common import (with_storage_client,
                                   transform_resource_name)


VSPHERE_STORAGE_FILE_NAME = 'vsphere_storage_file_name'


@operation
@with_storage_client
def create(ctx, storage_client, **kwargs):
    storage = {
        'name': ctx.node_id,
    }
    storage.update(ctx.properties['storage'])
    transform_resource_name(storage, ctx)

    storage_size = storage['storage_size']
    capabilities = ctx.capabilities.get_all().values()
    if not capabilities:
        raise RuntimeError('Error during trying to create storage:'
                           ' storage should be related to a VM,'
                           ' but capabilities are empty')
    if len(capabilities) > 1:
        raise RuntimeError('Error during trying to create storage:'
                           ' storage should be connected only to one VM')
    vm_name = capabilities[0]['node_id']
    storage_file_name = storage_client.create_storage(vm_name, storage_size)
    ctx[VSPHERE_STORAGE_FILE_NAME] = storage_file_name


@operation
@with_storage_client
def delete(ctx, storage_client, **kwargs):
    capabilities = ctx.capabilities.get_all().values()
    if not capabilities:
        raise RuntimeError('Error during trying to create storage:'
                           ' storage should be related to a VM,'
                           ' but capabilities are empty')
    if len(capabilities) > 1:
        raise RuntimeError('Error during trying to create storage:'
                           ' storage should be connected only to one VM')
    vm_name = capabilities[0]['node_id']
    storage_client.delete_storage(vm_name, ctx[VSPHERE_STORAGE_FILE_NAME])
