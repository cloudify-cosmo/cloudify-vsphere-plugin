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

from functools import wraps
import yaml
import os
import time

from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import atexit

from cloudify import ctx
from cloudify import exceptions as cfy_exc
from netaddr import IPNetwork

import re


TASK_CHECK_SLEEP = 15

PREFIX_RANDOM_CHARS = 3


def remove_runtime_properties(properties, context):
    for p in properties:
        if p in context.instance.runtime_properties:
            del context.instance.runtime_properties[p]


def transform_resource_name(res, ctx):

    if isinstance(res, basestring):
        res = {'name': res}

    if not isinstance(res, dict):
        raise ValueError("transform_resource_name() expects either string or "
                         "dict as the first parameter")

    pfx = ctx.bootstrap_context.resources_prefix

    if not pfx:
        return res['name']

    name = res['name']
    res['name'] = pfx + name

    if name.startswith(pfx):
        ctx.logger.warn("Prefixing resource '{0}' with '{1}' but it "
                        "already has this prefix".format(name, pfx))
    else:
        ctx.logger.info("Transformed resource name '{0}' to '{1}'".format(
                        name, res['name']))

    if name != res['name']:
        ctx.logger.info(
            'Updated resource name from {name} to {new_name}.'.format(
                name=res['name'],
                new_name=name,
            )
        )

    return res['name']


class Config(object):

    CONNECTION_CONFIG_PATH_DEFAULT = '~/connection_config.yaml'

    def get(self):
        cfg = {}
        which = self.__class__.which
        env_name = which.upper() + '_CONFIG_PATH'
        default_location_tpl = '~/' + which + '_config.yaml'
        default_location = os.path.expanduser(default_location_tpl)
        config_path = os.getenv(env_name, default_location)
        try:
            with open(config_path) as f:
                cfg = yaml.load(f.read())
        except IOError:
            ctx.logger.warn("Unable to read %s "
                            "configuration file %s." %
                            (which, config_path))

        return cfg


class ConnectionConfig(Config):
    which = 'connection'


class TestsConfig(Config):
    which = 'unit_tests'


class VsphereClient(object):

    config = ConnectionConfig

    def get(self, config=None, *args, **kw):
        static_config = self.__class__.config().get()
        cfg = {}
        cfg.update(static_config)
        if config:
            cfg.update(config)
        ret = self.connect(cfg)
        ret.format = 'yaml'
        return ret

    def connect(self, cfg):
        host = cfg['host']
        username = cfg['username']
        password = cfg['password']
        port = cfg['port']
        try:
            self.si = SmartConnect(host=host,
                                   user=username,
                                   pwd=password,
                                   port=int(port))
            atexit.register(Disconnect, self.si)
            return self
        except vim.fault.InvalidLogin:
            raise cfy_exc.NonRecoverableError(
                "Could not login to vSphere with provided credentials")

    def is_server_suspended(self, server):
        return server.summary.runtime.powerState.lower() == "suspended"

    def _get_content(self):
        if "content" not in locals():
            self.content = self.si.RetrieveContent()
        return self.content

    def get_obj_list(self, vimtype):
        content = self._get_content()
        container_view = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        objects = container_view.view
        container_view.Destroy()
        return objects

    def _has_parent(self, obj, parent_name, recursive):
        if parent_name is None:
            return True
        if obj.parent is not None:
            if obj.parent.name == parent_name:
                return True
            elif recursive:
                return self._has_parent(obj.parent, parent_name, recursive)
        # If we didn't confirm that the object has a parent by now, it doesn't
        return False

    def _get_obj_by_name(self, vimtype, name, parent_name=None,
                         recursive_parent=False):
        obj = None
        objects = self.get_obj_list(vimtype)
        for c in objects:
            if c.name.lower() == name.lower():
                if self._has_parent(c, parent_name, recursive_parent):
                    obj = c
                    break
        return obj

    def _get_obj_by_id(self, vimtype, id, parent_name=None,
                       recursive_parent=False):
        obj = None
        content = self._get_content()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        for c in container.view:
            if c._moId == id:
                if self._has_parent(c, parent_name, recursive_parent):
                    obj = c
                    break
        return obj

    def _wait_for_task(self, task):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(TASK_CHECK_SLEEP)
        if task.info.state != vim.TaskInfo.State.success:
            raise cfy_exc.NonRecoverableError(
                "Error during executing task on vSphere: '{0}'"
                .format(task.info.error))


class ServerClient(VsphereClient):

    def create_server(self,
                      auto_placement,
                      cpus,
                      datacenter_name,
                      memory,
                      networks,
                      resource_pool_name,
                      template_name,
                      vm_name,
                      os_type='linux',
                      domain=None,
                      dns_servers=None):
        ctx.logger.debug("Entering create_server with parameters %s"
                         % str(locals()))
        host, datastore = self.place_vm(auto_placement)

        ctx.logger.info("Using datastore %s for manager node." % datastore)
        devices = []
        adaptermaps = []

        datacenter = self._get_obj_by_name([vim.Datacenter],
                                           datacenter_name)
        if datacenter is None:
            msg = "Datacenter {0} could not be found".format(datacenter_name)
            ctx.logger.error(msg)
            raise cfy_exc.NonRecoverableError(msg)

        resource_pool = self._get_obj_by_name([vim.ResourcePool],
                                              resource_pool_name,
                                              host.name if host else None,
                                              recursive_parent=True)
        if resource_pool is None:
            msg = ("Resource pool {0} could not be found.".format(
                   resource_pool_name))
            ctx.logger.error(msg)
            raise cfy_exc.NonRecoverableError(msg)

        template_vm = self._get_obj_by_name([vim.VirtualMachine],
                                            template_name)
        if template_vm is None:
            msg = "VM template {0} could not be found.".format(template_name)
            ctx.logger.error(msg)
            raise cfy_exc.NonRecoverableError(msg)

        destfolder = datacenter.vmFolder
        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore
        relospec.pool = resource_pool
        if not auto_placement:
            relospec.host = host

        nicspec = vim.vm.device.VirtualDeviceSpec()
        for device in template_vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualVmxnet3):
                nicspec.device = device
                ctx.logger.warn('Removing network adapter from template. '
                                'Template should have no attached adapters.')
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.remove
                devices.append(nicspec)

        for network in networks:
            network_name = network['name']
            switch_distributed = network['switch_distributed']
            use_dhcp = network['use_dhcp']
            if switch_distributed:
                network_obj = self._get_obj_by_name(
                    [vim.dvs.DistributedVirtualPortgroup], network_name)
            else:
                network_obj = self._get_obj_by_name([vim.Network],
                                                    network_name)
            if network_obj is None:
                raise cfy_exc.NonRecoverableError(
                    'Network {0} could not be found'.format(network_name))
            nicspec = vim.vm.device.VirtualDeviceSpec()
            ctx.logger.info('Adding network interface on {name} to {server}'
                            .format(name=network_name,
                                    server=vm_name))
            nicspec.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.add
            nicspec.device = vim.vm.device.VirtualVmxnet3()
            if switch_distributed:
                info = vim.vm.device.VirtualEthernetCard\
                    .DistributedVirtualPortBackingInfo()
                nicspec.device.backing = info
                nicspec.device.backing.port =\
                    vim.dvs.PortConnection()
                nicspec.device.backing.port.switchUuid =\
                    network_obj.config.distributedVirtualSwitch.uuid
                nicspec.device.backing.port.portgroupKey =\
                    network_obj.key
            else:
                nicspec.device.backing = \
                    vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
                nicspec.device.backing.network = network_obj
                nicspec.device.backing.deviceName = network_name
            devices.append(nicspec)

            if use_dhcp:
                guest_map = vim.vm.customization.AdapterMapping()
                guest_map.adapter = vim.vm.customization.IPSettings()
                guest_map.adapter.ip = vim.vm.customization.DhcpIpGenerator()
                adaptermaps.append(guest_map)
            else:
                nw = IPNetwork(network["network"])
                guest_map = vim.vm.customization.AdapterMapping()
                guest_map.adapter = vim.vm.customization.IPSettings()
                guest_map.adapter.ip = vim.vm.customization.FixedIp()
                guest_map.adapter.ip.ipAddress = network['ip']
                guest_map.adapter.gateway = network["gateway"]
                guest_map.adapter.subnetMask = str(nw.netmask)
                adaptermaps.append(guest_map)

        vmconf = vim.vm.ConfigSpec()
        vmconf.numCPUs = cpus
        vmconf.memoryMB = memory
        vmconf.cpuHotAddEnabled = True
        vmconf.memoryHotAddEnabled = True
        vmconf.cpuHotRemoveEnabled = True
        vmconf.deviceChange = devices

        clonespec = vim.vm.CloneSpec()
        clonespec.location = relospec
        clonespec.config = vmconf
        clonespec.powerOn = True
        clonespec.template = False

        if adaptermaps:
            ctx.logger.info('Preparing OS customization spec for {server}'
                            .format(server=vm_name))
            customspec = vim.vm.customization.Specification()
            customspec.nicSettingMap = adaptermaps

            if os_type == 'linux':
                ident = vim.vm.customization.LinuxPrep()
                if domain:
                    ident.domain = domain
                ident.hostName = vim.vm.customization.FixedName()
                ident.hostName.name = vm_name
            elif os_type == 'windows':
                ident = vim.vm.customization.Sysprep()
                ident.userData = vim.vm.customization.UserData()
                ident.guiUnattended = vim.vm.customization.GuiUnattended()
                ident.identification = vim.vm.customization.Identification()
                ident.userData.computerName = vim.vm.customization.FixedName()
                ident.userData.computerName.name = vm_name
            else:
                raise cfy_exc.NonRecoverableError(
                    'os_type {os_type} was specified, but only "windows" and '
                    '"linux" are supported.'.format(os_type=os_type)
                )

            customspec.identity = ident

            globalip = vim.vm.customization.GlobalIPSettings()
            if dns_servers:
                globalip.dnsServerList = dns_servers
            customspec.globalIPSettings = globalip

            clonespec.customization = customspec
        ctx.logger.info('Cloning {server} from {template}.'
                        .format(server=vm_name, template=template_name))
        task = template_vm.Clone(folder=destfolder,
                                 name=vm_name,
                                 spec=clonespec)
        try:
            ctx.logger.debug("Task info: \n%s." %
                             "".join("%s: %s" % item
                                     for item in vars(task).items()))
            self._wait_vm_running(task)
        except task.info.error:
            raise cfy_exc.NonRecoverableError(
                "Error during executing VM creation task. VM name: \'{0}\'."
                .format(vm_name))
        return task.info.result

    def start_server(self, server):
        ctx.logger.debug("Entering server start procedure.")
        task = server.PowerOn()
        self._wait_for_task(task)
        ctx.logger.info("Server is now running.")

    def shutdown_server_guest(self, server):
        ctx.logger.debug("Entering server shutdown procedure.")
        server.ShutdownGuest()

    def stop_server(self, server):
        ctx.logger.debug("Entering stop server procedure.")
        task = server.PowerOff()
        self._wait_for_task(task)

    def is_server_poweredoff(self, server):
        return server.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.guest.guestState == "running"

    def delete_server(self, server):
        ctx.logger.debug("Entering server delete procedure.")
        if self.is_server_poweredon(server):
            ctx.logger.debug("Powering off server.")
            task = server.PowerOff()
            self._wait_for_task(task)
        task = server.Destroy()
        self._wait_for_task(task)

    def get_server_by_name(self, name):
        return self._get_obj_by_name([vim.VirtualMachine], name)

    def get_server_by_id(self, id):
        return self._get_obj_by_id([vim.VirtualMachine], id)

    def get_server_list(self):
        ctx.logger.debug("Entering server list procedure.")
        return self.get_obj_list([vim.VirtualMachine])

    def place_vm(self, auto_placement, except_datastores=[]):
        ctx.logger.debug("Entering place VM procedure.")
        selected_datastore = None
        selected_host = None
        selected_host_memory = 0
        selected_host_memory_used = 0
        datastore_list = self.get_obj_list([vim.Datastore])
        if len(except_datastores) == len(datastore_list):
            msg = ("Error during trying to place VM: "
                   "datastore and host can't be selected.")
            ctx.logger.error(msg)
            raise RuntimeError(msg)
        for datastore in datastore_list:
            if datastore._moId not in except_datastores:
                dtstr_free_spc = datastore.info.freeSpace
                if selected_datastore is None:
                    selected_datastore = datastore
                else:
                    selected_dtstr_free_spc = selected_datastore.info.freeSpace
                    if dtstr_free_spc > selected_dtstr_free_spc:
                        selected_datastore = datastore

        if selected_datastore is None:
            msg = "Error during placing VM: no datastore found."
            ctx.logger.error(msg)
            raise RuntimeError(msg)

        if auto_placement:
            ctx.logger.info('Using datastore {name}.'
                            .format(name=selected_datastore.name))
            return None, selected_datastore

        ctx.logger.info('Trying to use datastore {name} for deployment.'
                        .format(name=selected_datastore.name))

        for host_mount in selected_datastore.host:
            host = host_mount.key
            if host.overallStatus != vim.ManagedEntity.Status.red:
                if selected_host is None:
                    selected_host = host
                else:
                    host_memory = host.hardware.memorySize
                    host_memory_used = 0
                    for vm in host.vm:
                        if not vm.summary.config.template:
                            host_memory_used += vm.summary.config.memorySizeMB

                    host_memory_delta = host_memory - host_memory_used
                    selected_host_memory_delta =\
                        selected_host_memory - selected_host_memory_used
                    if host_memory_delta > selected_host_memory_delta:
                        selected_host = host
                        selected_host_memory = host_memory
                        selected_host_memory_used = host_memory_used
            else:
                ctx.logger.warn('Can not use host {name} for deployment. '
                                'Status is red.'
                                .format(name=selected_datastore.name))

        if selected_host is None:
            except_datastores.append(selected_datastore._moId)
            ctx.logger.warn('Not using datastore {datastore}. '
                            'No suitable host found.'
                            .format(datastore=selected_datastore.name))
            return self.place_vm(auto_placement, except_datastores)

        ctx.logger.info('Deploying to host {name} on datastore {datastore}'
                        .format(name=host.name,
                                datastore=selected_datastore.name))
        ctx.logger.debug("Selected datastore info: \n%s." %
                         "".join("%s: %s" % item
                                 for item in
                                 vars(selected_datastore).items()))
        ctx.logger.debug("Selected host info: \n%s." %
                         "".join("%s: %s" % item
                                 for item in
                                 vars(selected_host).items()))
        return selected_host, selected_datastore

    def resize_server(self, server, cpus=None, memory=None):
        ctx.logger.debug("Entering resize reconfiguration.")
        config = vim.vm.ConfigSpec()
        if cpus:
            config.numCPUs = cpus
        if memory:
            config.memoryMB = memory
        task = server.Reconfigure(spec=config)
        self._wait_for_task(task)
        ctx.logger.info("Server resized with new number of "
                        "CPUs: %s and RAM: %s." % (cpus, memory))

    def get_server_ip(self, vm, network_name):
        ctx.logger.info('Getting server IP from {network}.'
                        .format(network=network_name))
        # Linux appears to put the supplied (by DHCP) IP first,
        # while Windows puts it second.
        # This needs a lot more investigation and testing and may be subject
        # to timing issues.
        os_type = ctx.node.properties.get('os_family', 'linux')
        if os_type.lower() == 'windows':
            ip_position = 1
        else:
            ip_position = 0
        for network in vm.guest.net:
            if not network.network:
                ctx.logger.info('Ignoring device with MAC {mac} as it is not'
                                ' on a vSphere network.'
                                .format(mac=network.macAddress))
                continue
            if (network.network
                and network_name.lower() == network.network.lower()
                    and len(network.ipAddress) > 0):
                ctx.logger.info('Found {ip} from device with MAC {mac}'
                                .format(ip=network.ipAddress[0],
                                        mac=network.macAddress))
                return network.ipAddress[ip_position]

    def _wait_vm_running(self, task):
        self._wait_for_task(task)
        while not task.info.result.guest.guestState == "running"\
                or not task.info.result.guest.net:
            time.sleep(TASK_CHECK_SLEEP)


class NetworkClient(VsphereClient):

    def get_host_list(self):
        return self.get_obj_list([vim.HostSystem])

    def delete_port_group(self, name):
        ctx.logger.debug("Entering delete port procedure.")
        host_list = self.get_host_list()
        for host in host_list:
            host.configManager.networkSystem.RemovePortGroup(name)
        ctx.logger.info("Port %s was deleted." % name)

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Entering create port procedure.")
        host_list = self.get_host_list()
        for host in host_list:
            network_system = host.configManager.networkSystem
            specification = vim.host.PortGroup.Specification()
            specification.name = port_group_name
            specification.vlanId = vlan_id
            specification.vswitchName = vswitch_name
            vswitch = network_system.networkConfig.vswitch[0]
            specification.policy = vswitch.spec.policy
            ctx.logger.info('Adding port group {group_name} to vSwitch '
                            '{vswitch_name} on host {host_name}'
                            .format(group_name=port_group_name,
                                    vswitch_name=vswitch_name,
                                    host_name=host.name))
            network_system.AddPortGroup(specification)
        ctx.logger.info("Port was create successfully with "
                        "name: %s, "
                        "vLAN ID: %s, "
                        "vSwitch name: %s."
                        % (port_group_name, vlan_id, vswitch_name))

    def get_port_group_by_name(self, name):
        ctx.logger.debug("Entering get port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    ctx.logger.info("Port group(s) info: \n%s." %
                                    "".join("%s: %s" % item
                                            for item in
                                            vars(port_group).items()))
                    result.append(port_group)
        return result

    def create_dv_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Entering create dv port group procedure.")
        dv_port_group_type = 'earlyBinding'
        dvswitch = self._get_obj_by_name([vim.DistributedVirtualSwitch],
                                         vswitch_name)
        ctx.logger.debug("Distributed vSwitch info: \n%s." %
                         "".join("%s: %s" % item
                                 for item in
                                 vars(dvswitch).items()))
        vlan_spec = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(
            vlanId=vlan_id)
        port_settings = \
            vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
                vlan=vlan_spec)
        specification = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(
            name=port_group_name,
            defaultPortConfig=port_settings,
            type=dv_port_group_type)
        ctx.logger.info('Adding distributed port group {group_name} to '
                        'dvSwitch {dvswitch_name}'
                        .format(group_name=port_group_name,
                                dvswitch_name=vswitch_name))
        task = dvswitch.AddPortgroup(specification)
        self._wait_for_task(task)
        ctx.info("Port created.")

    def delete_dv_port_group(self, name):
        ctx.logger.debug("Entering delete dv port group.")
        dv_port_group = self.get_dv_port_group(name)
        task = dv_port_group.Destroy()
        self._wait_for_task(task)
        ctx.info("Port deleted.")

    def get_dv_port_group(self, name):
        dv_port_group = self._get_obj_by_name(
            [vim.dvs.DistributedVirtualPortgroup],
            name)
        return dv_port_group

    def add_network_interface(self, vm_id, network_name,
                              switch_distributed, mac_address=None):
        ctx.logger.debug("Entering add network interface procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        if self.is_server_suspended(vm):
            raise RuntimeError('Error during trying to add network'
                               ' interface: invalid VM state - \'suspended\'')

        devices = []
        if switch_distributed:
            network_obj = self._get_obj_by_name(
                [vim.dvs.DistributedVirtualPortgroup], network_name)
        else:
            network_obj = self._get_obj_by_name([vim.Network],
                                                network_name)
        nicspec = vim.vm.device.VirtualDeviceSpec()
        nicspec.operation = \
            vim.vm.device.VirtualDeviceSpec.Operation.add
        nicspec.device = vim.vm.device.VirtualVmxnet3()
        if mac_address:
            nicspec.device.macAddress = mac_address
        if switch_distributed:
            info = vim.vm.device.VirtualEthernetCard\
                .DistributedVirtualPortBackingInfo()
            nicspec.device.backing = info
            nicspec.device.backing.port =\
                vim.dvs.PortConnection()
            nicspec.device.backing.port.switchUuid =\
                network_obj.config.distributedVirtualSwitch.uuid
            nicspec.device.backing.port.portgroupKey =\
                network_obj.key
        else:
            nicspec.device.backing = \
                vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nicspec.device.backing.network = network_obj
            nicspec.device.backing.deviceName = network_name
        devices.append(nicspec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.info("Task info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(task).items()))
        self._wait_for_task(task)
        ctx.logger.info("Network interface was added.")

    def remove_network_interface(self, vm_id, network_name,
                                 switch_distributed):
        ctx.logger.debug("Entering remove network interface procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        if self.is_server_suspended(vm):
            raise RuntimeError('Error during trying to remove network'
                               ' interface: invalid VM state - \'suspended\'')

        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.remove
        devices = []
        device_to_delete = None

        if switch_distributed:
            network_obj = self._get_obj_by_name(
                [vim.dvs.DistributedVirtualPortgroup], network_name)
            for device in vm.config.hardware.device:
                if (isinstance(device, vim.vm.device.VirtualVmxnet3)
                    and device.backing.port.switchUuid ==
                        network_obj.config.distributedVirtualSwitch.uuid):
                    device_to_delete = device
        else:
            for device in vm.config.hardware.device:
                if (isinstance(device, vim.vm.device.VirtualVmxnet3)
                        and device.backing.deviceName == network_name):
                    device_to_delete = device

        if device_to_delete is None:
            raise cfy_exc.NonRecoverableError('Network interface not found')

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.info("Task info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(task).items()))
        self._wait_for_task(task)
        ctx.logger.info("Network interface was added.")


class StorageClient(VsphereClient):

    def create_storage(self, vm_id, storage_size):
        ctx.logger.debug("Entering create storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.info("VM info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(vm).items()))
        if self.is_server_suspended(vm):
            raise RuntimeError('Error during trying to create storage:'
                               ' invalid VM state - \'suspended\'')

        devices = []
        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.add
        virtual_device_spec.fileOperation =\
            vim.vm.device.VirtualDeviceSpec.FileOperation.create

        virtual_device_spec.device = vim.vm.device.VirtualDisk()
        virtual_device_spec.device.capacityInKB = storage_size*1024*1024
        virtual_device_spec.device.capacityInBytes =\
            storage_size*1024*1024*1024
        virtual_device_spec.device.backing =\
            vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        virtual_device_spec.device.backing.diskMode = 'Persistent'
        virtual_device_spec.device.backing.datastore = vm.datastore[0]

        vm_devices = vm.config.hardware.device
        vm_disk_filename = None
        vm_disk_filename_increment = 0
        vm_disk_filename_cur = None

        for vm_device in vm_devices:
            # Search all virtual disks
            if isinstance(vm_device, vim.vm.device.VirtualDisk):
                # Generate filename (add increment to VMDK base name)
                vm_disk_filename_cur = vm_device.backing.fileName
                p = re.compile('^(\[.*\]\s+.*\/.*)\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if vm_disk_filename is None:
                    vm_disk_filename = m.group(1)
                p = re.compile('^(.*)_([0-9]+)\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if m:
                    if m.group(2) is not None:
                        increment = int(m.group(2))
                        vm_disk_filename = m.group(1)
                        if increment > vm_disk_filename_increment:
                            vm_disk_filename_increment = increment

        # Exit error if VMDK filename undefined
        if vm_disk_filename is None:
            raise RuntimeError('Error during trying to create storage:'
                               ' Invalid VMDK name - \'{0}\''
                               .format(vm_disk_filename_cur))

        # Set target VMDK filename
        vm_disk_filename =\
            vm_disk_filename +\
            "_" + str(vm_disk_filename_increment + 1) +\
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
                num_controller += 1
                controller = vm_device
        if num_controller != 1:
            raise RuntimeError('Error during trying to create storage:'
                               ' SCSI controller cannot be found or'
                               ' is present more than once.')

        controller_key = controller.key

        # Set new unit number (7 cannot be used, and limit is 15)
        unit_number = None
        vm_vdisk_number = len(controller.device)
        if vm_vdisk_number < 7:
            unit_number = vm_vdisk_number
        elif vm_vdisk_number == 15:
            raise RuntimeError('Error during trying to create storage:'
                               ' one SCSI controller cannot have more'
                               ' than 15 virtual disks.')
        else:
            unit_number = vm_vdisk_number + 1

        virtual_device_spec.device.backing.fileName = vm_disk_filename
        virtual_device_spec.device.controllerKey = controller_key
        virtual_device_spec.device.unitNumber = unit_number
        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.info("Task info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(task).items()))
        self._wait_for_task(task)
        return vm_disk_filename

    def delete_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.info("VM info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(vm).items()))
        if self.is_server_suspended(vm):
            raise RuntimeError('Error during trying to delete storage:'
                               ' invalid VM state - \'suspended\'')

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
            raise cfy_exc.NonRecoverableError(
                'Error during trying to delete storage: storage not found')

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.info("Task info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(task).items()))
        self._wait_for_task(task)

    def get_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.info("VM info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(vm)))
        if vm:
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk)\
                        and device.backing.fileName == storage_file_name:
                    ctx.logger.info("Device info: \n%s." %
                                    "".join("%s: %s" % item
                                            for item in
                                            vars(device).items()))
                    return device
        return None

    def resize_storage(self, vm_id, storage_filename, storage_size):
        ctx.logger.debug("Entering resize storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.info("VM info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(vm).items()))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                'Error during trying to resize storage: invalid VM state'
                ' - \'suspended\'')

        disk_to_resize = None
        devices = vm.config.hardware.device
        for device in devices:
            if (isinstance(device, vim.vm.device.VirtualDisk)
                    and device.backing.fileName == storage_filename):
                disk_to_resize = device

        if disk_to_resize is None:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to resize storage: storage not found')

        updated_devices = []
        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.edit

        virtual_device_spec.device = disk_to_resize
        virtual_device_spec.device.capacityInKB = storage_size*1024*1024
        virtual_device_spec.device.capacityInBytes =\
            storage_size*1024*1024*1024

        updated_devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = updated_devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.info("VM info: \n%s." %
                        "".join("%s: %s" % item
                                for item in vars(vm).items()))
        self._wait_for_task(task)
        ctx.logger.info("Storage resized to a new size %s." % storage_size)


def with_server_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        server_client = ServerClient().get(config=config)
        kw['server_client'] = server_client
        return f(*args, **kw)
    return wrapper


def with_network_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        network_client = NetworkClient().get(config=config)
        kw['network_client'] = network_client
        return f(*args, **kw)
    return wrapper


def with_storage_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        storage_client = StorageClient().get(config=config)
        kw['storage_client'] = storage_client
        return f(*args, **kw)
    return wrapper
