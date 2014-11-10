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

from cloudify import ctx
from cloudify.decorators import operation
from cloudify import exceptions as cfy_exc
from server_plugin.server import VSPHERE_SERVER_ID
from vsphere_plugin_common import (with_storage_client,
                                   transform_resource_name,
                                   remove_runtime_properties)

VSPHERE_STORAGE_FILE_NAME = 'vsphere_storage_file_name'
VSPHERE_STORAGE_VM_ID = 'vsphere_storage_vm_id'
VSPHERE_STORAGE_RUNTIME_PROPERTIES = [VSPHERE_STORAGE_FILE_NAME,
                                      VSPHERE_STORAGE_VM_ID]


@operation
@with_storage_client
def create(storage_client, **kwargs):
    storage = {
        'name': ctx.node.id,
    }
    storage.update(ctx.node.properties['storage'])
    transform_resource_name(storage, ctx)

    storage_size = storage['storage_size']
    capabilities = ctx.capabilities.get_all().values()
    if not capabilities:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to create storage: storage should be '
            'related to a VM, but capabilities are empty')

    connected_vms = [rt_properties for rt_properties in capabilities
                     if VSPHERE_SERVER_ID in rt_properties]
    if len(connected_vms) > 1:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to create storage: storage should be '
            'connected only to one VM')

    vm_id = connected_vms[0][VSPHERE_SERVER_ID]
    storage_file_name = storage_client.create_storage(vm_id, storage_size)

    ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME] = \
        storage_file_name
    ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_ID] = vm_id


@operation
@with_storage_client
def delete(storage_client, **kwargs):
    vm_id = ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_ID]
    storage_file_name = \
        ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]
    storage_client.delete_storage(vm_id, storage_file_name)
    remove_runtime_properties(VSPHERE_STORAGE_RUNTIME_PROPERTIES, ctx)


@operation
@with_storage_client
def resize(storage_client, **kwargs):
    vm_id = ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_ID]
    storage_file_name = \
        ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]
    storage_size = ctx.instance.runtime_properties.get('storage_size')
    if not storage_size:
        raise cfy_exc.NonRecoverableError(
            'Error during trying to resize storage: new storage size wasn\'t'
            ' specified')
    storage_client.resize_storage(vm_id,
                                  storage_file_name,
                                  storage_size)
