########
# Copyright (c) 2016-2019 Cloudify Platform Ltd. All rights reserved
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

import pycdlib
import os
import re
from io import BytesIO

from cloudify import ctx

# This package imports
from cloudify_vsphere.utils import op
from vsphere_plugin_common import (
    with_rawvolume_client,
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    VSPHERE_STORAGE_RUNTIME_PROPERTIES,
    VSPHERE_STORAGE_IMAGE,
    VSPHERE_STORAGE_FILE_NAME,
    DATACENTER_ID,
)


def _joliet_name(name):
    if name[0] == "/":
        name = name[1:]
    return "/{name}".format(name=name[:64])


def _name_cleanup(name):
    return re.sub('[^A-Z0-9_/]{1}', r'_', name.upper())


def _iso_name(name):
    if name[0] == "/":
        name = name[1:]

    name_splited = name.split('.')
    if len(name_splited[-1]) <= 3 and len(name_splited) > 1:
        return "/{name}.{ext};3".format(
            name=_name_cleanup("_".join(name_splited[:-1])),
            ext=_name_cleanup(name_splited[-1]))
    else:
        return "/{name}.;3".format(name=_name_cleanup(name))


def _create_iso(vol_ident, sys_ident, files, files_raw, get_resource):
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3,
            vol_ident=vol_ident, sys_ident=sys_ident)

    if not files:
        files = {}

    # apply raw files over files content
    if files_raw:
        for name in files_raw:
            files[name] = get_resource(files_raw[name])

    # existed directories
    dirs = []

    # write file contents to cdrom image
    for name in files:
        file_bufer = BytesIO()
        file_bufer.write(files[name].encode())
        dir_path_spited = name.split("/")
        if len(dir_path_spited) > 1:
            initial_path = ""
            for sub_name in dir_path_spited[:-1]:
                initial_path = initial_path + "/" + sub_name
                if initial_path not in dirs:
                    iso.add_directory(_name_cleanup(initial_path),
                                      joliet_path=_joliet_name(initial_path))
                dirs.append(initial_path)
        iso.add_fp(file_bufer, len(files[name]),
                   _iso_name(name), joliet_path=_joliet_name(name))

    # finalize iso
    outiso = BytesIO()
    iso.write_fp(outiso)
    outiso.seek(0, os.SEEK_END)
    iso_size = outiso.tell()
    iso.close()
    outiso.seek(0, os.SEEK_SET)

    ctx.logger.info("ISO size: {size}".format(size=repr(iso_size)))

    return outiso


@op
@with_rawvolume_client
def create(rawvolume_client, files, files_raw, datacenter_name,
           allowed_datastores, allowed_datastore_ids,
           vol_ident, sys_ident, volume_prefix,
           raw_files=None, **kwargs):
    runtime_properties = ctx.instance.runtime_properties

    if runtime_properties.get(VSPHERE_STORAGE_FILE_NAME):
        ctx.logger.info('Instance is already created.')
        return

    ctx.logger.info("Creating new iso image.")

    if raw_files:
        ctx.logger.warn("`raw_files` is deprecated, use `files_raw`.")
        files_raw = files_raw.update(raw_files) if files_raw else raw_files

    outiso = _create_iso(vol_ident=vol_ident, sys_ident=sys_ident,
                         get_resource=ctx.get_resource, files=files,
                         files_raw=files_raw)

    iso_disk = "{prefix}/{name}.iso".format(
        prefix=volume_prefix, name=ctx.instance.id)
    datacenter_id, storage_file_name = rawvolume_client.upload_file(
            datacenter_name=datacenter_name,
            allowed_datastores=allowed_datastores,
            allowed_datastore_ids=allowed_datastore_ids,
            remote_file=iso_disk,
            data=outiso,
            host=ctx.node.properties['connection_config']['host'],
            port=ctx.node.properties['connection_config']['port'])
    runtime_properties[VSPHERE_STORAGE_IMAGE] = storage_file_name
    runtime_properties[VSPHERE_STORAGE_FILE_NAME] = storage_file_name
    runtime_properties[DATACENTER_ID] = datacenter_id


@op
@with_rawvolume_client
def delete(rawvolume_client, **kwargs):
    storage_file_name = ctx.instance.runtime_properties.get(
        VSPHERE_STORAGE_FILE_NAME)
    if not storage_file_name:
        return
    # backward compatibility with pre 2.16.1 version
    datacenter_name = kwargs.get('datacenter_name')
    # updated version with save selected datacenter
    datacenter_id = ctx.instance.runtime_properties.get(DATACENTER_ID)
    rawvolume_client.delete_file(datacenter_id=datacenter_id,
                                 datacenter_name=datacenter_name,
                                 datastorepath=storage_file_name)
    remove_runtime_properties(VSPHERE_STORAGE_RUNTIME_PROPERTIES, ctx)
