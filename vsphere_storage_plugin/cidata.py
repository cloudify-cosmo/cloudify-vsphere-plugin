########
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
import os

import cloudify_common_sdk.iso9660 as iso9660

from cloudify import ctx

# This package imports
from vsphere_plugin_common.utils import op, is_node_deprecated
from vsphere_plugin_common import with_rawvolume_client
from vsphere_plugin_common.constants import (
    VSPHERE_STORAGE_IMAGE,
    VSPHERE_STORAGE_FILE_NAME,
    DATACENTER_ID
)


@op
@with_rawvolume_client
def create(rawvolume_client,
           files,
           files_raw,
           datacenter_name,
           allowed_datastores,
           allowed_datastore_ids,
           vol_ident,
           sys_ident,
           volume_prefix,
           raw_files=None,
           **_):
    is_node_deprecated(ctx.node.type)
    if ctx.instance.runtime_properties.get(VSPHERE_STORAGE_FILE_NAME):
        ctx.logger.info('Instance is already created.')
        return

    ctx.logger.info('Creating new iso image.')

    if raw_files:
        ctx.logger.warn('`raw_files` is deprecated, use `files_raw`.')
        files_raw = files_raw.update(raw_files) if files_raw else raw_files

    outiso = iso9660.create_iso(vol_ident=vol_ident, sys_ident=sys_ident,
                                get_resource=ctx.get_resource, files=files,
                                files_raw=files_raw)

    outiso.seek(0, os.SEEK_END)
    iso_size = outiso.tell()
    outiso.seek(0, os.SEEK_SET)

    ctx.logger.info("ISO size: {size}".format(size=repr(iso_size)))

    iso_disk = "{prefix}/{name}.iso".format(
        prefix=volume_prefix, name=ctx.instance.id)
    datacenter_id, storage_path = rawvolume_client.upload_file(
        datacenter_name=datacenter_name,
        allowed_datastores=allowed_datastores,
        allowed_datastore_ids=allowed_datastore_ids,
        remote_file=iso_disk,
        data=outiso,
        host=ctx.node.properties['connection_config']['host'],
        port=ctx.node.properties['connection_config']['port'])
    ctx.instance.runtime_properties[VSPHERE_STORAGE_IMAGE] = storage_path
    ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME] = storage_path
    ctx.instance.runtime_properties[DATACENTER_ID] = datacenter_id


@op
@with_rawvolume_client
def delete(rawvolume_client, **kwargs):
    storage_path = ctx.instance.runtime_properties.get(
        VSPHERE_STORAGE_FILE_NAME)
    if not storage_path:
        return
    # backward compatibility with pre 2.16.1 version
    datacenter_name = kwargs.get('datacenter_name')
    # updated version with save selected datacenter
    datacenter_id = ctx.instance.runtime_properties.get(DATACENTER_ID)
    rawvolume_client.delete_file(datacenter_id=datacenter_id,
                                 datacenter_name=datacenter_name,
                                 datastorepath=storage_path)
    # clear the runtime after delete to support edge cases of failure
    ctx.instance.runtime_properties.pop(VSPHERE_STORAGE_FILE_NAME, None)


@op
@with_rawvolume_client
def delete_iso(rawvolume_client,
               use_external_resource,
               force_delete,
               **kwargs):
    storage_path = ctx.instance.runtime_properties.get(
        VSPHERE_STORAGE_FILE_NAME)
    if not storage_path:
        return
    if use_external_resource and not force_delete:
        ctx.logger.info('Skip to delete external resource')
    else:
        # backward compatibility with pre 2.16.1 version
        datacenter_name = kwargs.get('datacenter_name')
        # updated version with save selected datacenter
        datacenter_id = ctx.instance.runtime_properties.get(DATACENTER_ID)
        rawvolume_client.delete_file(datacenter_id=datacenter_id,
                                     datacenter_name=datacenter_name,
                                     datastorepath=storage_path)
        # clear the runtime after delete to support edge cases of failure
        ctx.instance.runtime_properties.pop(VSPHERE_STORAGE_FILE_NAME, None)


@op
@with_rawvolume_client
def upload_iso(rawvolume_client,
               datacenter_name,
               allowed_datastores,
               allowed_datastore_ids,
               volume_prefix,
               iso_file_path,
               use_external_resource,
               **_):
    is_node_deprecated(ctx.node.type)
    if ctx.instance.runtime_properties.get(VSPHERE_STORAGE_FILE_NAME):
        ctx.logger.info('Instance is already created.')
        return
    if not use_external_resource:
        iso_disk = "{prefix}/{name}.iso".format(
            prefix=volume_prefix, name=ctx.instance.id)
        with open(iso_file_path, "rb") as file_data:
            datacenter_id, storage_path = rawvolume_client.upload_file(
                datacenter_name=datacenter_name,
                allowed_datastores=allowed_datastores,
                allowed_datastore_ids=allowed_datastore_ids,
                remote_file=iso_disk,
                data=file_data,
                host=ctx.node.properties['connection_config']['host'],
                port=ctx.node.properties['connection_config']['port'])
    else:
        datacenter_id, storage_path = rawvolume_client.file_exist_in_vsphere(
            datacenter_name=datacenter_name,
            allowed_datastores=allowed_datastores,
            allowed_datastore_ids=allowed_datastore_ids,
            remote_file=iso_file_path,
            host=ctx.node.properties['connection_config']['host'],
            port=ctx.node.properties['connection_config']['port'])
    ctx.instance.runtime_properties[VSPHERE_STORAGE_IMAGE] = storage_path
    ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME] = storage_path
    ctx.instance.runtime_properties[DATACENTER_ID] = datacenter_id
