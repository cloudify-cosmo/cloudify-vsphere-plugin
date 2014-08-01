__author__ = 'Oleksandr_Raskosov'

from cloudify.decorators import operation
from vsphere_plugin_common import with_storage_client


VSPHERE_STORAGE_FILE_NAME = 'vsphere_storage_file_name'


@operation
@with_storage_client
def create(ctx, storage_client, **kwargs):
    storage = {
        'name': ctx.node_id,
    }
    storage.update(ctx.properties['storage'])

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
