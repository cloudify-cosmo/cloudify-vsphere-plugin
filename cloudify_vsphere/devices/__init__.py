########
# Copyright (c) 2018-2020 Cloudify Platform Ltd. All rights reserved
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

from copy import deepcopy

from pyVmomi import vim

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from vsphere_plugin_common.utils import (
    op,
    find_rels_by_type,
    is_node_deprecated)
from vsphere_plugin_common.clients.server import (
    ServerClient,
    set_boot_order)
from vsphere_plugin_common.clients.network import ControllerClient
from vsphere_plugin_common import (
    run_deferred_task,
    with_server_client,
    remove_runtime_properties)
from vsphere_plugin_common.constants import (
    IP,
    NETWORK_NAME,
    VSPHERE_SERVER_ID,
    SWITCH_DISTRIBUTED,
    VSPHERE_SERVER_CONNECTED_NICS)

RELATIONSHIP_NIC_TO_NETWORK = \
    'cloudify.relationships.vsphere.nic_connected_to_network'


def add_connected_network(node_instance, nic_properties=None):
    nets_from_rels = find_rels_by_type(
        node_instance, RELATIONSHIP_NIC_TO_NETWORK)
    if len(nets_from_rels) > 1:
        raise NonRecoverableError(
            'Currently only one relationship of type {0} '
            'is supported per node.'.format(RELATIONSHIP_NIC_TO_NETWORK))
    elif len(nets_from_rels) < 1:
        ctx.logger.debug('No NIC to network relationships found.')
        return
    net_from_rel = nets_from_rels[0]
    network_name = \
        net_from_rel.target.instance.runtime_properties.get(
            NETWORK_NAME, nic_properties.get('name'))
    if network_name:
        connected_network = {
            'name': network_name,
            'switch_distributed':
            net_from_rel.target.instance.runtime_properties.get(
                SWITCH_DISTRIBUTED)
        }
    else:
        ctx.logger.error('The target network does not have an ID.')
        return
    nic_configuration = nic_properties.get('network_configuration')
    mac_address = nic_properties.get('mac_address')
    if mac_address:
        connected_network['mac_address'] = mac_address
    if nic_configuration:
        connected_network.update(nic_configuration)
    node_instance.runtime_properties['connected_network'] = connected_network


def controller_without_connected_networks(runtime_properties):
    controller_properties = deepcopy(runtime_properties)

    try:
        del controller_properties['connected_networks']
        del controller_properties['connected']
    except KeyError:
        pass

    return controller_properties


@operation(resumable=True)
def create_controller(ctx, **kwargs):
    is_node_deprecated(ctx.node.type)
    controller_properties = ctx.instance.runtime_properties
    controller_properties.update(kwargs)
    ctx.logger.info("Properties {0}".format(repr(controller_properties)))
    add_connected_network(ctx.instance, controller_properties)


@operation(resumable=True)
def delete_controller(**kwargs):
    remove_runtime_properties()


@operation(resumable=True)
def attach_scsi_controller(ctx, **kwargs):
    if 'busKey' in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.source.instance.runtime_properties['busKey']))
        return
    scsi_properties = controller_without_connected_networks(
        ctx.source.instance.runtime_properties)
    hostvm_properties = ctx.target.instance.runtime_properties
    ctx.logger.debug("Source {0}".format(repr(scsi_properties)))
    ctx.logger.debug("Target {0}".format(repr(hostvm_properties)))

    cl = ControllerClient()
    cl.get(config=ctx.source.node.properties.get("connection_config"))

    run_deferred_task(cl, ctx.source.instance)

    scsi_spec, controller_type = cl.generate_scsi_card(
        scsi_properties, hostvm_properties.get(VSPHERE_SERVER_ID))

    controller_settings = cl.attach_controller(
        hostvm_properties.get(VSPHERE_SERVER_ID),
        scsi_spec, controller_type,
        instance=ctx.source.instance)

    ctx.logger.info("Controller attached with {buskey} key.".format(
        buskey=controller_settings['busKey']))

    ctx.source.instance.runtime_properties.update(controller_settings)
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def attach_ethernet_card(ctx, **kwargs):
    if 'busKey' in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.source.instance.runtime_properties['busKey']))
        return
    attachment = _attach_ethernet_card(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        controller_without_connected_networks(
            ctx.source.instance.runtime_properties),
        instance=ctx.target.instance)
    ctx.source.instance.runtime_properties.update(attachment)
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def attach_server_to_ethernet_card(ctx, **kwargs):
    if 'busKey' in ctx.target.instance.runtime_properties:
        ctx.logger.info("Controller attached with {buskey} key.".format(
            buskey=ctx.target.instance.runtime_properties['busKey']))
        return
    if ctx.target.instance.id not in \
            ctx.source.instance.runtime_properties.get(
                VSPHERE_SERVER_CONNECTED_NICS, []):
        attachment = _attach_ethernet_card(
            ctx.target.node.properties.get("connection_config"),
            ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
            controller_without_connected_networks(
                ctx.target.instance.runtime_properties),
            instance=ctx.target.instance)
        ctx.target.instance.runtime_properties.update(attachment)
        ctx.target.instance.runtime_properties.dirty = True
        ctx.target.instance.update()
    ip = _get_card_ip(
        ctx.source.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('name'))
    ctx.source.instance.runtime_properties[IP] = ip
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def detach_controller(ctx, **kwargs):
    if 'busKey' not in ctx.source.instance.runtime_properties:
        ctx.logger.info("Controller was not attached, skipping.")
        return
    _detach_controller(
        ctx.source.node.properties.get("connection_config"),
        ctx.target.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.source.instance.runtime_properties.get('busKey'),
        instance=ctx.source.instance)
    del ctx.source.instance.runtime_properties['busKey']


@operation(resumable=True)
def detach_server_from_controller(ctx, **kwargs):
    if ctx.target.instance.id in \
            ctx.source.instance.runtime_properties.get(
                VSPHERE_SERVER_CONNECTED_NICS, []):
        return
    if 'busKey' not in ctx.target.instance.runtime_properties:
        ctx.logger.info("Controller was not attached, skipping.")
        return
    _detach_controller(
        ctx.target.node.properties.get("connection_config"),
        ctx.source.instance.runtime_properties.get(VSPHERE_SERVER_ID),
        ctx.target.instance.runtime_properties.get('busKey'),
        instance=ctx.target.instance)
    del ctx.target.instance.runtime_properties['busKey']


def _attach_ethernet_card(client_config,
                          server_id,
                          ethernet_card_properties,
                          instance):
    cl = ControllerClient()
    cl.get(config=client_config)
    run_deferred_task(cl, instance)
    nicspec, controller_type = cl.generate_ethernet_card(
        ethernet_card_properties)
    return cl.attach_controller(server_id, nicspec, controller_type,
                                instance=instance)


def _detach_controller(client_config, server_id, bus_key, instance):
    cl = ControllerClient()
    cl.get(config=client_config)
    run_deferred_task(cl, instance)
    cl.detach_controller(server_id, bus_key, instance)


def _get_card_ip(client_config, server_id, nic_name):
    server_client = ServerClient()
    server_client.get(config=client_config)
    vm = server_client.get_server_by_id(server_id)
    return server_client.get_server_ip(vm, nic_name, ignore_local=False)


def temp_stop_server(cl, server, instance):
    if server.obj.summary.runtime.powerState.lower() == "poweredoff":
        return
    task = server.obj.PowerOff()
    cl._wait_for_task(task, instance=instance)


def temp_start_server(cl, server, instance):
    if server.obj.summary.runtime.powerState.lower() == "poweredon":
        return
    task = server.obj.PowerOn()
    cl._wait_for_task(task, instance=instance)


@operation(resumable=True)
def copy_device_properties(ctx, **kwargs):
    ctx.instance.runtime_properties.update(kwargs)


@operation(resumable=True)
def clean_device_properties(**kwargs):
    remove_runtime_properties()


def get_usb_physical_path(content, vm_host_name, device_name):
    cv = content.viewManager.CreateContainerView(
        container=content.rootFolder, type=[vim.HostSystem],
        recursive=True)
    container = content.viewManager.CreateContainerView(
        container=content.rootFolder, type=[vim.ComputeResource],
        recursive=True)
    for host in cv.view:
        # let's make sure that we are checking against the VM host
        if host.name != vm_host_name:
            continue
        for cluster_cont in container.view:
            for resource_container in cluster_cont.host:
                if host.name != resource_container.name:
                    continue
                host_info = \
                    cluster_cont.environmentBrowser.QueryConfigTarget(host)
                if len(host_info.usb) > 0:
                    for usb in host_info.usb:
                        if usb.description == device_name:
                            return usb.physicalPath
    container.Destroy()
    cv.Destroy()


def check_if_vm_has_usb_controller(vm, controller_type):
    for device in vm.config.hardware.device:
        if isinstance(device, controller_type):
            return True
    return False


@operation(resumable=True)
def attach_usb_device(ctx, **kwargs):
    if '__attached' in ctx.source.instance.runtime_properties:
        ctx.logger.info('USB device was attached')
        return
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    device_name = get_usb_physical_path(cl.si.content,
                                        vm.summary.runtime.host.name,
                                        device_name_from_props)
    if not device_name:
        raise NonRecoverableError(
            'usb device {0} not found on vm host {1}'.format(
                device_name_from_props,
                vm.summary.runtime.host.name
            )
        )
    device_changes = []
    usb_device_type = {
        'usb2': vim.VirtualUSBController,
        'usb3': vim.VirtualUSBXHCIController
    }
    usb_type = ctx.source.node.properties.get('controller_type')
    has_controller = check_if_vm_has_usb_controller(
        vm,
        usb_device_type.get(usb_type)
    )
    # adding controller if needed
    if not has_controller:
        controller_spec = vim.VirtualDeviceConfigSpec()
        controller_spec.operation = \
            vim.VirtualDeviceConfigSpecOperation.add
        controller_spec.device = usb_device_type.get(usb_type)()
        if usb_type == 'usb2':
            controller_spec.device.key = 7000
        elif usb_type == 'usb3':
            controller_spec.device.key = 14000
        device_changes.append(controller_spec)
    usb_spec = vim.VirtualDeviceConfigSpec()
    usb_spec.operation = vim.VirtualDeviceConfigSpecOperation.add
    usb_spec.device = vim.VirtualUSB()
    usb_spec.device.backing = vim.VirtualUSB.USBBackingInfo()
    usb_spec.device.backing.deviceName = device_name
    device_changes.append(usb_spec)
    config_spec = vim.vm.ConfigSpec()
    config_spec.deviceChange = device_changes
    task = vm.obj.ReconfigVM_Task(spec=config_spec)
    cl._wait_for_task(task, instance=ctx.source.instance)
    ctx.source.instance.runtime_properties['__attached'] = True
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def detach_usb_device(ctx, **kwargs):
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    usb_device = None
    for device in vm.config.hardware.device:
        if isinstance(device, vim.VirtualUSB) and \
                device.deviceInfo.summary == device_name_from_props:
            usb_device = device
            break
    if usb_device:
        dev_changes = []
        device_spec = vim.VirtualDeviceConfigSpec()
        device_spec.operation = vim.VirtualDeviceConfigSpecOperation.remove
        device_spec.device = usb_device
        dev_changes.append(device_spec)
        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = dev_changes
        task = vm.obj.ReconfigVM_Task(spec=config_spec)
        cl._wait_for_task(task, instance=ctx.source.instance)


@operation(resumable=True)
def attach_serial_port(ctx, **kwargs):
    if '__attached' in ctx.source.instance.runtime_properties:
        ctx.logger.info('Serial Port was attached')
        return
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    device_changes = []
    serial_spec = vim.VirtualDeviceConfigSpec()
    serial_spec.operation = vim.VirtualDeviceConfigSpecOperation.add
    serial_spec.device = vim.VirtualSerialPort()
    serial_spec.device.yieldOnPoll = True
    serial_spec.device.backing = \
        vim.VirtualSerialPort.DeviceBackingInfo()
    serial_spec.device.backing.deviceName = device_name_from_props
    device_changes.append(serial_spec)
    config_spec = vim.vm.ConfigSpec()
    config_spec.deviceChange = device_changes
    if ctx.source.node.properties.get('turn_off_vm', False):
        temp_stop_server(cl, vm, ctx.target.instance)
        task = vm.obj.ReconfigVM_Task(spec=config_spec)
        cl._wait_for_task(task, instance=ctx.source.instance)
        temp_start_server(cl, vm, ctx.target.instance)
    else:
        if vm.obj.summary.runtime.powerState.lower() == "poweredon":
            raise NonRecoverableError(
                'Serial Port can\'t be attached while VM is running')
        else:
            ctx.logger.info(
                'VM is poweredoff and will not be started automatically')
            task = vm.obj.ReconfigVM_Task(spec=config_spec)
            cl._wait_for_task(task, instance=ctx.source.instance)

    ctx.source.instance.runtime_properties['__attached'] = True
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def detach_serial_port(ctx, **kwargs):
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    serial_port = None
    for device in vm.config.hardware.device:
        if isinstance(device, vim.VirtualSerialPort) and \
                device.deviceInfo.summary == device_name_from_props:
            serial_port = device
            break
    if serial_port:
        dev_changes = []
        device_spec = vim.VirtualDeviceConfigSpec()
        device_spec.operation = vim.VirtualDeviceConfigSpecOperation.remove
        device_spec.device = serial_port
        dev_changes.append(device_spec)
        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = dev_changes
        if ctx.source.node.properties.get('turn_off_vm', False):
            temp_stop_server(cl, vm, ctx.target.instance)
            task = vm.obj.ReconfigVM_Task(spec=config_spec)
            cl._wait_for_task(task, instance=ctx.source.instance)
            temp_start_server(cl, vm, ctx.target.instance)
        else:
            if vm.obj.summary.runtime.powerState.lower() == "poweredon":
                raise NonRecoverableError(
                    'Serial Port can\'t be detached while VM is running')
            else:
                ctx.logger.info(
                    'VM is poweredoff and will not be started automatically')
                task = vm.obj.ReconfigVM_Task(spec=config_spec)
                cl._wait_for_task(task, instance=ctx.source.instance)
        del ctx.source.instance.runtime_properties['__attached']


def get_pci_device(content, vm_host_name, device_name):
    cv = content.viewManager.CreateContainerView(
        container=content.rootFolder, type=[vim.HostSystem],
        recursive=True)
    container = content.viewManager.CreateContainerView(
        container=content.rootFolder, type=[vim.ComputeResource],
        recursive=True)
    for host in cv.view:
        # let's make sure that we are checking against the VM host
        if host.name != vm_host_name:
            continue
        for cluster_cont in container.view:
            for resource_container in cluster_cont.host:
                if host.name != resource_container.name:
                    continue
                host_info = \
                    cluster_cont.environmentBrowser.QueryConfigTarget(host)
                if len(host_info.pciPassthrough) > 0:
                    for pci in host_info.pciPassthrough:
                        if pci.pciDevice.deviceName == device_name:
                            return pci
    container.Destroy()
    cv.Destroy()


@operation(resumable=True)
def attach_pci_device(ctx, **kwargs):
    if '__attached' in ctx.source.instance.runtime_properties:
        ctx.logger.info('PCI device was attached')
        return
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    pci_device = get_pci_device(cl.si.content,
                                vm.summary.runtime.host.name,
                                device_name_from_props)
    if not pci_device:
        raise NonRecoverableError(
            'pci device {0} not found on vm host {1}'.format(
                device_name_from_props,
                vm.summary.runtime.host.name
            )
        )
    device_changes = []
    device_id = hex(pci_device.pciDevice.deviceId % 2**16).lstrip('0x')
    pci_spec = vim.VirtualDeviceConfigSpec()
    pci_spec.operation = vim.VirtualDeviceConfigSpecOperation.add
    pci_spec.device = vim.VirtualPCIPassthrough()
    pci_spec.device.backing = vim.VirtualPCIPassthroughDeviceBackingInfo()
    pci_spec.device.backing.deviceId = device_id
    pci_spec.device.backing.id = pci_device.pciDevice.id
    pci_spec.device.backing.systemId = pci_device.systemId
    pci_spec.device.backing.vendorId = pci_device.pciDevice.vendorId
    pci_spec.device.backing.deviceName = pci_device.pciDevice.deviceName
    device_changes.append(pci_spec)
    config_spec = vim.vm.ConfigSpec()
    config_spec.memoryReservationLockedToMax = True
    config_spec.deviceChange = device_changes
    if ctx.source.node.properties.get('turn_off_vm', False):
        temp_stop_server(cl, vm, ctx.target.instance)
        task = vm.obj.ReconfigVM_Task(spec=config_spec)
        cl._wait_for_task(task, instance=ctx.source.instance)
        temp_start_server(cl, vm, ctx.target.instance)
    else:
        if vm.obj.summary.runtime.powerState.lower() == "poweredon":
            raise NonRecoverableError(
                'PCI Device can\'t be attached while VM is running')
        else:
            ctx.logger.info(
                'VM is poweredoff and will not be started automatically')
            task = vm.obj.ReconfigVM_Task(spec=config_spec)
            cl._wait_for_task(task, instance=ctx.source.instance)
    ctx.source.instance.runtime_properties['__attached'] = True
    ctx.source.instance.runtime_properties.dirty = True
    ctx.source.instance.update()


@operation(resumable=True)
def detach_pci_device(ctx, **kwargs):
    vsphere_server_id = ctx.target.instance.runtime_properties.get(
        'vsphere_server_id')
    connection_config_props = ctx.source.node.properties.get(
        'connection_config')
    device_name_from_props = ctx.source.node.properties.get('device_name')
    cl = ServerClient()
    cl.get(config=connection_config_props)
    vm = cl._get_obj_by_id(vim.VirtualMachine,
                           vsphere_server_id)
    pci_details = get_pci_device(cl.si.content,
                                 vm.summary.runtime.host.name,
                                 device_name_from_props)
    pci_device = None
    for device in vm.config.hardware.device:
        if isinstance(device, vim.VirtualPCIPassthrough) and \
                device.backing.id == pci_details.pciDevice.id:
            pci_device = device
            break
    if pci_device:
        dev_changes = []
        device_spec = vim.VirtualDeviceConfigSpec()
        device_spec.operation = vim.VirtualDeviceConfigSpecOperation.remove
        device_spec.device = pci_device
        dev_changes.append(device_spec)
        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = dev_changes
        if ctx.source.node.properties.get('turn_off_vm', False):
            temp_stop_server(cl, vm, ctx.target.instance)
            task = vm.obj.ReconfigVM_Task(spec=config_spec)
            cl._wait_for_task(task, instance=ctx.source.instance)
            temp_start_server(cl, vm, ctx.target.instance)
        else:
            if vm.obj.summary.runtime.powerState.lower() == "poweredon":
                raise NonRecoverableError(
                    'PCI Device can\'t be detached while VM is running')
            else:
                ctx.logger.info(
                    'VM is poweredoff and will not be started automatically')
                task = vm.obj.ReconfigVM_Task(spec=config_spec)
                cl._wait_for_task(task, instance=ctx.source.instance)
        del ctx.source.instance.runtime_properties['__attached']


@op
@with_server_client
def change_boot_order(ctx, server_client, boot_order,
                      disk_keys=None, ethernet_keys=None, **_):
    """
        The task to change vm boot order:
        param: boot_order: list of devices to boot
            valid values:
                - cdrom
                - disk
                - ethernet
                - floppy
        param: disk_keys: list of disk keys
            (optional - when empty and disk device is present in boot order the
            hdd disk keys will be set as a keys)
        param: ethernet_keys: list of ethernet keys
            (optional - when empty and ethernet device is present in boot order
             the ethernet keys will be set as a keys)
    """
    vsphere_server_id = ctx.instance.runtime_properties.get(
        'vsphere_server_id')
    set_boot_order(ctx=ctx, server_client=server_client,
                   server_id=vsphere_server_id, boot_order=boot_order,
                   disk_keys=disk_keys, ethernet_keys=ethernet_keys)


@op
@with_server_client
def remove_cdrom(ctx, server_client, **_):
    vsphere_server_id = ctx.instance.runtime_properties.get(
        'vsphere_server_id')
    vm = server_client._get_obj_by_id(vim.VirtualMachine, vsphere_server_id)
    cdrom_spec = None
    for device in vm.obj.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualCdrom):
            cdrom_spec = vim.vm.device.VirtualDeviceSpec()
            cdrom_spec.device = device
            cdrom_spec.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.remove
            break
    if cdrom_spec:
        vm_conf = vim.vm.ConfigSpec(deviceChange=[cdrom_spec])
        task = vm.obj.ReconfigVM_Task(vm_conf)
        server_client._wait_for_task(task, instance=ctx.instance)
