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


from __future__ import division

# Stdlib imports
import re

# Third party imports
import requests
from pyVmomi import vim

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError, OperationRetry

# This package imports
from . import VsphereClient
from .._compat import text_type
from ..utils import prepare_for_log


class RawVolumeClient(VsphereClient):

    def delete_file(self, datacenter_name=None, datastorepath=None,
                    datacenter_id=None):
        if datacenter_id:
            dc = self._get_obj_by_id(vim.Datacenter, datacenter_id)
        else:
            dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter_name}/{datacenter_id}"
                .format(datacenter_name=text_type(datacenter_name),
                        datacenter_id=text_type(datacenter_id)))
        self.si.content.fileManager.DeleteFile(datastorepath, dc.obj)

    def upload_file(self, datacenter_name, allowed_datastores,
                    allowed_datastore_ids, remote_file, data, host,
                    port):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=text_type(datacenter_name)))
        self._logger.debug(
            "Will check storage with IDs: {ids}; and names: {names}"
            .format(ids=text_type(allowed_datastore_ids),
                    names=text_type(allowed_datastores)))

        datastores = self._get_datastores()
        ds = None
        if not allowed_datastores and not allowed_datastore_ids and datastores:
            ds = datastores[0]
        else:
            # select by datastore ids
            if allowed_datastore_ids:
                for datastore in datastores:
                    if datastore.id in allowed_datastore_ids:
                        ds = datastore
                        break
            # select by datastore names
            if not ds and allowed_datastores:
                for datastore in datastores:
                    if datastore.name in allowed_datastores:
                        ds = datastore
                        break
        if not ds:
            raise NonRecoverableError(
                "Unable to get datastore {allowed} in {available}"
                .format(allowed=text_type(allowed_datastores),
                        available=text_type([datastore.name
                                             for datastore in datastores])))

        params = {"dsName": ds.name,
                  "dcPath": dc.name}
        http_url = 'https://{host}:{port}/folder/{remote_file}'.format(
            host=host, port=text_type(port), remote_file=remote_file)

        # Get the cookie built from the current session
        client_cookie = self.si._stub.cookie
        # Break apart the cookie into it's component parts - This is more than
        # is needed, but a good example of how to break apart the cookie
        # anyways. The verbosity makes it clear what is happening.
        cookie_name = client_cookie.split("=", 1)[0]
        cookie_value = client_cookie.split("=", 1)[1].split(";", 1)[0]
        cookie_path = client_cookie.split("=", 1)[1].split(";", 1)[1].split(
            ";", 1)[0].lstrip()
        cookie_text = " " + cookie_value + "; $" + cookie_path
        # Make a cookie
        cookie = dict()
        cookie[cookie_name] = cookie_text

        response = requests.put(
            http_url,
            params=params,
            data=data,
            headers={'Content-Type': 'application/octet-stream'},
            cookies=cookie,
            verify=False)
        response.raise_for_status()
        return dc.id, "[{datastore}] {file_name}".format(
            datastore=ds.name, file_name=remote_file)

    def file_exist_in_vsphere(self, datacenter_name, allowed_datastores,
                              allowed_datastore_ids, remote_file, host, port):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=text_type(datacenter_name)))
        self._logger.debug(
            "Will check storage with IDs: {ids}; and names: {names}"
            .format(ids=text_type(allowed_datastore_ids),
                    names=text_type(allowed_datastores)))

        datastores = self._get_datastores()
        ds = None
        if not allowed_datastores and not allowed_datastore_ids and datastores:
            ds = datastores[0]
        else:
            # select by datastore ids
            if allowed_datastore_ids:
                for datastore in datastores:
                    if datastore.id in allowed_datastore_ids:
                        ds = datastore
                        break
            # select by datastore names
            if not ds and allowed_datastores:
                for datastore in datastores:
                    if datastore.name in allowed_datastores:
                        ds = datastore
                        break
        if not ds:
            raise NonRecoverableError(
                "Unable to get datastore {allowed} in {available}"
                .format(allowed=text_type(allowed_datastores),
                        available=text_type([datastore.name
                                             for datastore in datastores])))

        path_file = remote_file.split(' ')[-1]
        params = {"dsName": ds.name,
                  "dcPath": dc.name}
        http_url = 'https://{host}:{port}/folder/{remote_file}'.format(
            host=host, port=text_type(port), remote_file=path_file)

        # Get the cookie built from the current session
        client_cookie = self.si._stub.cookie
        # Break apart the cookie into it's component parts - This is more than
        # is needed, but a good example of how to break apart the cookie
        # anyways. The verbosity makes it clear what is happening.
        cookie_name = client_cookie.split("=", 1)[0]
        cookie_value = client_cookie.split("=", 1)[1].split(";", 1)[0]
        cookie_path = client_cookie.split("=", 1)[1].split(";", 1)[1].split(
            ";", 1)[0].lstrip()
        cookie_text = " " + cookie_value + "; $" + cookie_path
        # Make a cookie
        cookie = dict()
        cookie[cookie_name] = cookie_text

        response = requests.head(
            http_url,
            params=params,
            headers={'Content-Type': 'application/octet-stream'},
            cookies=cookie,
            verify=False)
        if response.status_code == 200:
            return dc.id, remote_file
        elif response.status_code == 404:
            raise NonRecoverableError(
                "Vsphere file: {0} does not exist.".format(remote_file))
        else:
            raise OperationRetry(
                'Cannot access. Error: {0}'.format(response.status_code))


class StorageClient(VsphereClient):

    def create_storage(self,
                       vm_id,
                       storage_size,
                       parent_key,
                       mode,
                       thin_provision=False,
                       max_wait_time=300,
                       **_):

        self._logger.debug("Entering create storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        if not vm:
            raise NonRecoverableError("Unable to get vm: {vm_id}"
                                      .format(vm_id=vm_id))
        self._logger.debug("VM info: \n{}".format(vm))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
                'Error during trying to create storage:'
                ' invalid VM state - \'suspended\''
            )

        vm_disk_filename = ctx.instance.runtime_properties.get('vm_disk_name')
        # we don't have name for new disk
        if not vm_disk_filename:
            devices = []
            virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
            virtual_device_spec.operation =\
                vim.vm.device.VirtualDeviceSpec.Operation.add
            virtual_device_spec.fileOperation =\
                vim.vm.device.VirtualDeviceSpec.FileOperation.create

            virtual_device_spec.device = vim.vm.device.VirtualDisk()
            virtual_device_spec.device.capacityInKB = \
                storage_size * 1024 * 1024
            virtual_device_spec.device.capacityInBytes =\
                storage_size * 1024 * 1024 * 1024
            virtual_device_spec.device.backing =\
                vim.vm.device.VirtualDisk.FlatVer2BackingInfo()

            virtual_device_spec.device.backing.diskMode = mode
            virtual_device_spec.device.backing.thinProvisioned = thin_provision
            virtual_device_spec.device.backing.datastore = vm.datastore[0].obj

            vm_devices = vm.config.hardware.device
            vm_disk_filename = None
            vm_disk_filename_increment = 0
            vm_disk_filename_cur = None

            for vm_device in vm_devices:
                # Search all virtual disks
                if isinstance(vm_device, vim.vm.device.VirtualDisk):
                    # Generate filename (add increment to VMDK base name)
                    vm_disk_filename_cur = vm_device.backing.fileName
                    p = re.compile('^(\\[.*\\]\\s+.*\\/.*)\\.vmdk$')
                    m = p.match(vm_disk_filename_cur)
                    if vm_disk_filename is None:
                        vm_disk_filename = m.group(1)
                    p = re.compile('^(.*)_([0-9]+)\\.vmdk$')
                    m = p.match(vm_disk_filename_cur)
                    if m:
                        if m.group(2) is not None:
                            increment = int(m.group(2))
                            vm_disk_filename = m.group(1)
                            if increment > vm_disk_filename_increment:
                                vm_disk_filename_increment = increment

            # Exit error if VMDK filename undefined
            if not vm_disk_filename:
                raise NonRecoverableError(
                    'Error during trying to create storage:'
                    ' Invalid VMDK name - \'{0}\''.format(vm_disk_filename_cur)
                )

            # Set target VMDK filename
            vm_disk_filename =\
                vm_disk_filename +\
                "_" + text_type(vm_disk_filename_increment + 1) +\
                ".vmdk"

            # Search virtual SCSI controller
            controller = None
            num_controller = 0
            controller_types = (
                vim.vm.device.VirtualBusLogicController,
                vim.vm.device.VirtualLsiLogicController,
                vim.vm.device.VirtualLsiLogicSASController,
                vim.vm.device.ParaVirtualSCSIController)
            for vm_device in vm_devices:
                if isinstance(vm_device, controller_types):
                    if parent_key < 0:
                        num_controller += 1
                        controller = vm_device
                    else:
                        if parent_key == vm_device.key:
                            num_controller = 1
                            controller = vm_device
                            break
            if num_controller != 1:
                raise NonRecoverableError(
                    'Error during trying to create storage: '
                    'SCSI controller cannot be found or is present more than '
                    'once.'
                )

            controller_key = controller.key

            # Set new unit number (7 cannot be used, and limit is 15)
            vm_vdisk_number = len(controller.device)
            if vm_vdisk_number < 7:
                unit_number = vm_vdisk_number
            elif vm_vdisk_number == 15:
                raise NonRecoverableError(
                    'Error during trying to create storage: one SCSI '
                    'controller cannot have more than 15 virtual disks.'
                )
            else:
                unit_number = vm_vdisk_number + 1

            virtual_device_spec.device.backing.fileName = vm_disk_filename
            virtual_device_spec.device.controllerKey = controller_key
            virtual_device_spec.device.unitNumber = unit_number
            devices.append(virtual_device_spec)

            config_spec = vim.vm.ConfigSpec()
            config_spec.deviceChange = devices

            task = vm.obj.Reconfigure(spec=config_spec)

            ctx.instance.runtime_properties['vm_disk_name'] = vm_disk_filename
            ctx.instance.runtime_properties.dirty = True
            ctx.instance.update()
            self._wait_for_task(task, max_wait_time=max_wait_time)
        # remove old vm disk name
        del ctx.instance.runtime_properties['vm_disk_name']
        ctx.instance.runtime_properties.dirty = True
        ctx.instance.update()

        # Get the SCSI bus and unit IDs
        scsi_controllers = []
        disks = []
        # Use the device list from the platform rather than the cache because
        # we just created a disk so it won't be in the cache
        for device in vm.obj.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualSCSIController):
                scsi_controllers.append(device)
            elif isinstance(device, vim.vm.device.VirtualDisk):
                disks.append(device)
        # Find the disk we just created
        bus_id = None
        for disk in disks:
            if disk.backing.fileName == vm_disk_filename:
                unit = disk.unitNumber
                for controller in scsi_controllers:
                    if controller.key == disk.controllerKey:
                        bus_id = controller.busNumber
                        break
                # We found the right disk, we can't do any better than this
                break
        if bus_id is None:
            raise NonRecoverableError(
                'Could not find SCSI bus ID for disk with filename: '
                '{file_name}'.format(file_name=vm_disk_filename)
            )
        else:
            # Give the SCSI ID in the usual format, e.g. 0:1
            scsi_id = ':'.join((text_type(bus_id), text_type(unit)))

        return vm_disk_filename, scsi_id

    def delete_storage(self,
                       vm_id,
                       storage_file_name,
                       max_wait_time=300):
        self._logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        self._logger.debug("VM info: \n{}".format(vm))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
                "Error during trying to delete storage: invalid VM state - "
                "'suspended'"
            )

        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.remove
        virtual_device_spec.fileOperation =\
            vim.vm.device.VirtualDeviceSpec.FileOperation.destroy

        devices = []

        device_to_delete = None

        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualDisk)\
                    and device.backing.fileName == storage_file_name:
                device_to_delete = device

        if device_to_delete is None:
            self._logger.debug("Storage removed on previous step.")
            return

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.obj.Reconfigure(spec=config_spec)
        self._wait_for_task(task, max_wait_time=max_wait_time)

    def get_storage(self, vm_id, storage_file_name):
        self._logger.debug("Entering get storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        self._logger.debug("VM info: \n{}".format(vm))
        if vm:
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk)\
                        and device.backing.fileName == storage_file_name:
                    self._logger.debug('Device info: \n{0}.'.format(
                        prepare_for_log(vars(device))))
                    return device
        return

    def resize_storage(self,
                       vm_id,
                       storage_filename,
                       storage_size,
                       max_wait_time=300):
        self._logger.debug("Entering resize storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        self._logger.debug("VM info: \n{}".format(vm))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
                'Error during trying to resize storage: invalid VM state'
                ' - \'suspended\'')

        disk_to_resize = None
        devices = vm.config.hardware.device
        for device in devices:
            if isinstance(device, vim.vm.device.VirtualDisk) and \
                    device.backing.fileName == storage_filename:
                disk_to_resize = device

        if disk_to_resize is None:
            raise NonRecoverableError(
                'Error during trying to resize storage: storage not found.')

        storage_size_e2 = storage_size * 1024 * 1024
        storage_size_e3 = storage_size * 1024 * 1024 * 1024

        if disk_to_resize.capacityInKB == storage_size_e2 and \
                disk_to_resize.capacityInBytes == storage_size_e3:
            self._logger.debug(
                'Storage size is {storage_size}'.format(
                    storage_size=storage_size))
            return
        updated_devices = []
        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation = \
            vim.vm.device.VirtualDeviceSpec.Operation.edit

        virtual_device_spec.device = disk_to_resize
        virtual_device_spec.device.capacityInKB = storage_size_e2
        virtual_device_spec.device.capacityInBytes = storage_size_e3

        updated_devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = updated_devices

        task = vm.obj.Reconfigure(spec=config_spec)
        self._wait_for_task(task, max_wait_time=max_wait_time)
        self._logger.debug(
            'Storage resized to a new size {storage_size}.'.format(
                storage_size=storage_size))
