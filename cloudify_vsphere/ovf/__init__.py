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
import os
import ssl
import time
import tarfile

from threading import Timer

# Third party imports
from pyVmomi import vim, vmodl

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common import with_server_client
from vsphere_plugin_common.clients.server import ServerClient
from vsphere_plugin_common.utils import op
from vsphere_plugin_common import (
    remove_runtime_properties,
)
from vsphere_plugin_common.constants import (
    VSPHERE_SERVER_ID,
)
from vsphere_plugin_common._compat import Request, urlopen


def get_tarfile_size(tarfile):
    if hasattr(tarfile, 'size'):
        return tarfile.size
    size = tarfile.seek(0, 2)
    tarfile.seek(0, 0)
    return size


class OvfHandler(object):
    def __init__(self, logger, ovafile):
        self.logger = logger
        self.handle = self._create_file_handle(ovafile)
        self.tarfile = tarfile.open(fileobj=self.handle)
        ovffilename = list(
            [x for x in self.tarfile.getnames() if x.endswith(".ovf")])[0]
        ovffile = self.tarfile.extractfile(ovffilename)
        self.descriptor = ovffile.read().decode()

    def _create_file_handle(self, entry):
        if os.path.exists(entry):
            return FileHandle(entry)
        return WebHandle(entry)

    def get_descriptor(self):
        return self.descriptor

    def set_spec(self, spec):
        self.spec = spec

    def get_disk(self, file_item):
        ovffilename = list(
            [x for x in self.tarfile.getnames() if x == file_item.path])[0]
        return self.tarfile.extractfile(ovffilename)

    def get_device_url(self, file_item, lease):
        for device_url in lease.info.deviceUrl:
            if device_url.importKey == file_item.deviceId:
                return device_url
        raise Exception(
            "Failed to find deviceUrl for file {0}".format(file_item.path))

    def upload_disks(self, lease, content):
        self.lease = lease
        try:
            self.start_timer()
            for fileItem in self.spec.fileItem:
                self.upload_disk(fileItem, lease, content)
            lease.Complete()
            self.logger.debug("Finished deploy successfully.")
        except vmodl.MethodFault as mfex:
            lease.Abort(mfex)
            raise NonRecoverableError(
                "Hit an error in upload: {0}".format(mfex))
        except Exception as ex:
            lease.Abort(vmodl.fault.SystemError(reason=str(ex)))
            raise NonRecoverableError(
                "Hit an error in upload: {0}".format(ex))

    def get_esxi_host_ip(self, content, host_name):
        host_ip = ''
        cv = content.viewManager.CreateContainerView(
            container=content.rootFolder, type=[vim.HostSystem],
            recursive=True)
        for child in cv.view:
            if child.name == host_name:
                separateOct = (".")
                managment_ip = child.summary.managementServerIp
                ipNo4Oct = '.'.join(managment_ip.split(separateOct)[0:3])
                for i in child.config.network.vnic:
                    if i.spec.ip.ipAddress.find(ipNo4Oct) > -1:
                        host_ip = i.spec.ip.ipAddress
                        break
        cv.Destroy()
        return host_ip

    def upload_disk(self, file_item, lease, content):
        ovffile = self.get_disk(file_item)
        if ovffile is None:
            return
        device_url = self.get_device_url(file_item, lease)
        start = device_url.url.find('://') + 3
        end = device_url.url.find('/', start)
        node_name = device_url.url[start:end]
        node_ip = self.get_esxi_host_ip(content, node_name)
        url = device_url.url.replace(node_name, node_ip)
        headers = {'Content-length': get_tarfile_size(ovffile)}
        if hasattr(ssl, '_create_unverified_context'):
            ssl_context = ssl._create_unverified_context()
        else:
            ssl_context = None
        req = Request(url, ovffile, headers)
        urlopen(req, context=ssl_context)

    def start_timer(self):
        Timer(5, self.timer).start()

    def timer(self):
        try:
            prog = self.handle.progress()
            self.lease.Progress(prog)
            if self.lease.state not in [vim.HttpNfcLease.State.done,
                                        vim.HttpNfcLease.State.error]:
                self.start_timer()
            self.logger.debug("Progress: %d%%\r" % prog)
        except Exception:
            pass


class FileHandle(object):
    def __init__(self, filename):
        self.filename = filename
        self.fh = open(filename, 'rb')

        self.st_size = os.stat(filename).st_size
        self.offset = 0

    def __del__(self):
        self.fh.close()

    def tell(self):
        return self.fh.tell()

    def seek(self, offset, whence=0):
        if whence == 0:
            self.offset = offset
        elif whence == 1:
            self.offset += offset
        elif whence == 2:
            self.offset = self.st_size - offset

        return self.fh.seek(offset, whence)

    def seekable(self):
        return True

    def read(self, amount):
        self.offset += amount
        result = self.fh.read(amount)
        return result

    def progress(self):
        return int(100.0 * self.offset // self.st_size)


class WebHandle(object):
    def __init__(self, url):
        self.url = url
        r = urlopen(url)
        if r.code != 200:
            raise FileNotFoundError(url)
        self.headers = self._headers_to_dict(r)
        if 'accept-ranges' not in self.headers:
            raise Exception("Site does not accept ranges")
        self.st_size = int(self.headers['content-length'])
        self.offset = 0

    def _headers_to_dict(self, r):
        result = {}
        if hasattr(r, 'getheaders'):
            for n, v in r.getheaders():
                result[n.lower()] = v.strip()
        else:
            for line in r.info().headers:
                if line.find(':') != -1:
                    n, v = line.split(': ', 1)
                    result[n.lower()] = v.strip()
        return result

    def tell(self):
        return self.offset

    def seek(self, offset, whence=0):
        if whence == 0:
            self.offset = offset
        elif whence == 1:
            self.offset += offset
        elif whence == 2:
            self.offset = self.st_size - offset
        return self.offset

    def seekable(self):
        return True

    def read(self, amount):
        start = self.offset
        end = self.offset + amount - 1
        req = Request(self.url,
                      headers={'Range': 'bytes=%d-%d' % (start, end)})
        r = urlopen(req)
        self.offset += amount
        result = r.read(amount)
        r.close()
        return result

    def progress(self):
        return int(100.0 * self.offset // self.st_size)


def get_obj_in_list(obj_name, obj_list):
    for o in obj_list:
        if o.name == obj_name:
            return o
    raise NonRecoverableError('Could not find {0}'.format(obj_name))


@op
def create(ctx, connection_config, target, ovf_name, ovf_source,
           datastore_name, disk_provisioning, network_mappings,
           memory, cpus):
    esxi_node = target.get('host')
    vm_folder = target.get('folder')
    resource_pool = target.get('resource_pool')
    client = ServerClient(ctx_logger=ctx.logger).get(
        config=connection_config)
    datacenter = client.si.content.rootFolder.childEntity[0]

    if not resource_pool:
        resource_pool = connection_config.get("resource_pool_name")

    resource_pool = get_obj_in_list(resource_pool,
                                    client._get_resource_pools())
    if vm_folder:
        vm_folder = get_obj_in_list(vm_folder, client._get_vm_folders()).obj
    else:
        vm_folder = datacenter.vmFolder
    host = None
    if esxi_node:
        host = get_obj_in_list(esxi_node, client._get_hosts()).obj

    datastore = get_obj_in_list(datastore_name, client._get_datastores())
    ovf_handle = OvfHandler(ctx.logger, ovf_source)

    nma = vim.OvfManager.NetworkMapping.Array()
    for network in network_mappings:
        interface_name = network.get('key')
        network_name = network.get('value')
        network = get_obj_in_list(network_name, datacenter.network)
        nm = vim.OvfManager.NetworkMapping(name=interface_name,
                                           network=network)
        nma.append(nm)

    spec_params = vim.OvfManager.CreateImportSpecParams(
        entityName=ovf_name,
        diskProvisioning=disk_provisioning,
        networkMapping=nma
    )
    if esxi_node:
        spec_params.hostSystem = host
    import_spec = client.si.content.ovfManager.CreateImportSpec(
        ovf_handle.get_descriptor(), resource_pool.obj,
        datastore.obj, spec_params
    )

    if import_spec.error:
        raise NonRecoverableError(
            "Got these errors {0}".format(import_spec.error))

    ovf_handle.set_spec(import_spec)
    if esxi_node:
        lease = resource_pool.obj.ImportVApp(import_spec.importSpec,
                                             vm_folder,
                                             host)
    else:
        lease = resource_pool.obj.ImportVApp(import_spec.importSpec,
                                             vm_folder)

    while lease.state == vim.HttpNfcLease.State.initializing:
        ctx.logger.debug("Waiting for lease to be ready...")
        time.sleep(1)
    if lease.state == vim.HttpNfcLease.State.error:
        raise NonRecoverableError("Lease error: {0}".format(lease.error))
    if lease.state == vim.HttpNfcLease.State.done:
        raise NonRecoverableError("lease state is done couldn't upload files")

    ovf_handle.upload_disks(lease, client.si.content)
    created_vm = client._get_obj_by_name(vim.VirtualMachine, ovf_name,
                                         use_cache=False)
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = created_vm.id
    vmconf = vim.vm.ConfigSpec()
    if cpus:
        vmconf.numCPUs = cpus
    if memory:
        vmconf.memoryMB = memory
    vmconf.cpuHotAddEnabled = True
    vmconf.memoryHotAddEnabled = True
    vmconf.cpuHotRemoveEnabled = True
    task = created_vm.obj.ReconfigVM_Task(spec=vmconf)
    client._wait_for_task(task)
    client.start_server(created_vm)


@op
@with_server_client
def delete(server_client, ctx, ovf_name, max_wait_time=300):
    runtime_properties = ctx.instance.runtime_properties
    vm_id = runtime_properties[VSPHERE_SERVER_ID]
    server_obj = server_client.get_server_by_id(vm_id)
    ctx.logger.info('Preparing to delete server {name}'.format(name=ovf_name))
    server_client.delete_server(server_obj, max_wait_time=max_wait_time)
    ctx.logger.info('Successfully deleted server {name}'.format(name=ovf_name))
    remove_runtime_properties()
