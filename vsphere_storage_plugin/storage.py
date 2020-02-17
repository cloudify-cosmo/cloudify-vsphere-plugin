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

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

# This package imports
from cloudify_vsphere.utils import op
from vsphere_plugin_common import (
    with_storage_client,
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    VSPHERE_SERVER_ID,
    VSPHERE_STORAGE_SIZE,
    VSPHERE_STORAGE_VM_ID,
    VSPHERE_STORAGE_VM_NAME,
    VSPHERE_STORAGE_SCSI_ID,
    VSPHERE_STORAGE_FILE_NAME,
    VSPHERE_STORAGE_RUNTIME_PROPERTIES,
)
from cloudify_vsphere.utils.feedback import prepare_for_log


@op
@with_storage_client
def create(storage_client, storage, use_external_resource=False):
    ctx.logger.debug("Entering create storage procedure.")
    storage.setdefault('name', ctx.node.id)
    # This should be debug, but left as info until CFY-4867 makes logs more
    # visible
    ctx.logger.info(
        'Storage properties: {properties}'.format(
            properties=prepare_for_log(storage),
        )
    )
    storage_size = storage['storage_size']
    parent_key = storage.get('parent_key', -1)
    mode = storage.get('mode', "persistent")
    thin_provision = storage.get('thin_provision', False)

    capabilities = ctx.capabilities.get_all().values()
    if not capabilities:
        raise NonRecoverableError(
            'Error during trying to create storage: storage should be '
            'related to a VM, but capabilities are empty.')

    connected_vms = [rt_properties for rt_properties in capabilities
                     if VSPHERE_SERVER_ID in rt_properties]
    if len(connected_vms) > 1:
        raise NonRecoverableError(
            'Error during trying to create storage: storage may be '
            'connected to at most one VM')

    vm_id = connected_vms[0][VSPHERE_SERVER_ID]
    vm_name = connected_vms[0]['name']
    if use_external_resource:
        for fname in [
            VSPHERE_STORAGE_SCSI_ID, VSPHERE_STORAGE_FILE_NAME,
            VSPHERE_STORAGE_SIZE
        ]:
            if fname not in storage:
                raise NonRecoverableError(
                    'You should provide {}'.format(fname))
            else:
                ctx.instance.runtime_properties[fname] = storage[fname]
        ctx.logger.info(
            "Reuse volume on VM '{vm}' with name '{name}'".format(
                vm=vm_name,
                name=storage['name']
            )
        )
        ctx.instance.runtime_properties['use_external_resource'] = True
    else:
        storage_file_name = ctx.instance.runtime_properties.get(
            VSPHERE_STORAGE_FILE_NAME)
        scsi_id = ctx.instance.runtime_properties.get(VSPHERE_STORAGE_SCSI_ID)
        if storage_file_name:
            ctx.logger.info(
                "Storage attached on VM '{vm}' with file name "
                "'{file_name}' and SCSI ID: {scsi} ".format(
                    vm=vm_name,
                    file_name=storage_file_name,
                    scsi=scsi_id,
                )
            )
            return

        ctx.logger.info(
            "Creating new volume on VM '{vm}' with name '{name}' and size: "
            "{size}".format(
                vm=vm_name,
                name=storage['name'],
                size=storage_size
            )
        )

        try:
            storage_file_name, scsi_id = storage_client.create_storage(
                vm_id,
                storage_size,
                parent_key,
                mode,
                thin_provision,
            )
        except NonRecoverableError as e:
            # If more than one storage is attached to the same VM, there is
            # a race and they might try to use the same name. If that happens
            # the loser will retry.
            if 'vim.fault.FileAlreadyExists' in str(e):
                ctx.operation.retry('Name clash with another storage. '
                                    'Retrying')
                return
            raise

        ctx.logger.info(
            "Storage successfully created on VM '{vm}' with file name "
            "'{file_name}' and SCSI ID: {scsi} ".format(
                vm=vm_name,
                file_name=storage_file_name,
                scsi=scsi_id,
            )
        )
        ctx.instance.runtime_properties[VSPHERE_STORAGE_SCSI_ID] = scsi_id
        ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME] = \
            storage_file_name
    ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_ID] = vm_id
    ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_NAME] = vm_name


@op
@with_storage_client
def delete(storage_client, **kwargs):
    if ctx.instance.runtime_properties.get('use_external_resource'):
        ctx.logger.info('Used existing resource.')
        remove_runtime_properties(VSPHERE_STORAGE_RUNTIME_PROPERTIES, ctx)
        return

    vm_id = ctx.instance.runtime_properties.get(VSPHERE_STORAGE_VM_ID)
    vm_name = ctx.instance.runtime_properties.get(VSPHERE_STORAGE_VM_NAME)
    if not vm_name or not vm_id:
        ctx.logger.info(
            'Storage deletion not needed due to not being fully initialized.')
        return

    storage_file_name = \
        ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]
    ctx.logger.info(
        "Deleting storage {file} from {vm}".format(
            file=storage_file_name,
            vm=vm_name,
        )
    )
    storage_client.delete_storage(vm_id, storage_file_name)
    ctx.logger.info(
        "Successfully deleted storage {file} from {vm}".format(
            file=storage_file_name,
            vm=vm_name,
        )
    )
    remove_runtime_properties(VSPHERE_STORAGE_RUNTIME_PROPERTIES, ctx)


@op
@with_storage_client
def resize(storage_client, **kwargs):
    vm_id = ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_ID]
    vm_name = ctx.instance.runtime_properties[VSPHERE_STORAGE_VM_NAME]
    storage_file_name = \
        ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]
    storage_size = ctx.instance.runtime_properties.get('storage_size')
    if not storage_size:
        raise NonRecoverableError(
            'Error during trying to resize storage: new storage size wasn\'t'
            ' specified.')
    ctx.logger.info(
        "Resizing storage {file} on {vm} to {new_size}".format(
            file=storage_file_name,
            vm=vm_name,
            new_size=storage_size,
        )
    )
    storage_client.resize_storage(vm_id,
                                  storage_file_name,
                                  storage_size)
    ctx.logger.info(
        "Successfully resized storage {file} on {vm} to {new_size}".format(
            file=storage_file_name,
            vm=vm_name,
            new_size=storage_size,
        )
    )
