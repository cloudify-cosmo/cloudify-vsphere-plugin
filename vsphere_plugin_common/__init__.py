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
import re
import atexit

from constants import (
    TASK_CHECK_SLEEP,
    NETWORKS,
)

from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
from cloudify import ctx
from cloudify import exceptions as cfy_exc
from netaddr import IPNetwork


def prepare_for_log(inputs):
    result = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            value = prepare_for_log(value)

        if 'password' in key:
            value = '**********'

        result[key] = value
    return result


def get_ip_from_vsphere_nic_ips(nic):
    for ip in nic.ipAddress:
        if ip.startswith('169.254.') or ip.lower().startswith('fe80::'):
            # This is a locally assigned IPv4 or IPv6 address and thus we
            # will assume it is not routable
            ctx.logger.debug('Found locally assigned IP {ip}. '
                             'Skipping.'.format(ip=ip))
            continue
        else:
            return ip
    # No valid IP was found
    return None


def remove_runtime_properties(properties, context):
    for p in properties:
        if p in context.instance.runtime_properties:
            del context.instance.runtime_properties[p]


class Config(object):

    # Required during vsphere manager bootstrap
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
                "Could not login to vSphere on {host} with provided "
                "credentials".format(host=host)
            )

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

    def get_vm_networks(self, vm):
        """
            Get details of every network interface on a VM.
            A list of dicts with the following network interface information
            will be returned:
            {
                'name': Name of the network,
                'distributed': True if the network is distributed, otherwise
                               False,
                'mac': The MAC address as provided by vsphere,
            }
        """
        nics = []
        ctx.logger.debug('Getting NIC list')
        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                nics.append(dev)

        ctx.logger.debug('Got NICs: {nics}'.format(nics=nics))
        networks = []
        for nic in nics:
            ctx.logger.debug('Checking details for NIC {nic}'.format(nic=nic))
            distributed = hasattr(nic.backing, 'port') and isinstance(
                nic.backing.port,
                vim.dvs.PortConnection,
            )

            network_name = None
            if distributed:
                mapping_id = nic.backing.port.portgroupKey
                ctx.logger.debug(
                    'Found NIC was on distributed port group with port group '
                    'key {key}'.format(key=mapping_id)
                )
                for network in vm.network:
                    if hasattr(network, 'key'):
                        ctx.logger.debug(
                            'Checking for match on network with key: '
                            '{key}'.format(key=network.key)
                        )
                        if mapping_id == network.key:
                            network_name = network.name
                            ctx.logger.debug(
                                'Found NIC was distributed and was on '
                                'network {network}'.format(
                                    network=network_name,
                                )
                            )
            else:
                # If not distributed, the port group name can be retrieved
                # directly
                network_name = nic.backing.deviceName
                ctx.logger.debug(
                    'Found NIC was on port group {network}'.format(
                        network=network_name,
                    )
                )

            if network_name is None:
                raise cfy_exc.NonRecoverableError(
                    'Could not get network name for device with MAC address '
                    '{mac} on VM {vm}'.format(mac=nic.macAddress, vm=vm.name)
                )

            networks.append({
                'name': network_name,
                'distributed': distributed,
                'mac': nic.macAddress,
            })

        return networks


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
                         % prepare_for_log(locals()))
        host, datastore = self.place_vm(auto_placement)

        # This should be debug, but left as info until CFY-4867 makes logs
        # more visible
        ctx.logger.info("Using datastore %s for manager node." % datastore)
        devices = []
        adaptermaps = []

        datacenter = self._get_obj_by_name([vim.Datacenter],
                                           datacenter_name)
        if datacenter is None:
            msg = "Datacenter {0} could not be found".format(datacenter_name)
            raise cfy_exc.NonRecoverableError(msg)

        resource_pool = self._get_obj_by_name([vim.ResourcePool],
                                              resource_pool_name,
                                              host.name if host else None,
                                              recursive_parent=True)
        if resource_pool is None:
            msg = ("Resource pool {0} could not be found.".format(
                   resource_pool_name))
            raise cfy_exc.NonRecoverableError(msg)

        template_vm = self._get_obj_by_name([vim.VirtualMachine],
                                            template_name)
        if template_vm is None:
            msg = "VM template {0} could not be found.".format(template_name)
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
            # Info level as this is something that was requested in the
            # blueprint
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
            ctx.logger.debug(
                'Preparing OS customization spec for {server}'.format(
                    server=vm_name,
                )
            )
            customspec = vim.vm.customization.Specification()
            customspec.nicSettingMap = adaptermaps

            if os_type is None or os_type == 'linux':
                ident = vim.vm.customization.LinuxPrep()
                if domain:
                    ident.domain = domain
                ident.hostName = vim.vm.customization.FixedName()
                ident.hostName.name = vm_name
            elif os_type == 'windows':
                props = ctx.node.properties

                password = props.get('windows_password')
                if not password:
                    agent_config = props.get('agent_config', {})
                    password = agent_config.get('password')

                if not password:
                    raise cfy_exc.NonRecoverableError(
                        'When using Windows, a password must be set. '
                        'Please set either properties.windows_password '
                        'or properties.agent_config.password'
                    )
                # We use GMT without daylight savings if no timezone is
                # supplied, as this is as close to UTC as we can do
                timezone = props.get('windows_timezone', 90)

                ident = vim.vm.customization.Sysprep()
                ident.userData = vim.vm.customization.UserData()
                ident.guiUnattended = vim.vm.customization.GuiUnattended()
                ident.identification = vim.vm.customization.Identification()

                # Configure userData
                ident.userData.computerName = vim.vm.customization.FixedName()
                ident.userData.computerName.name = vm_name
                # Without these vars, customization is silently skipped
                # but deployment 'succeeds'
                ident.userData.fullName = vm_name
                ident.userData.orgName = "Organisation"
                ident.userData.productId = ""

                # Configure guiUnattended
                ident.guiUnattended.autoLogon = False
                ident.guiUnattended.password = vim.vm.customization.Password()
                ident.guiUnattended.password.plainText = True
                ident.guiUnattended.password.value = password
                ident.guiUnattended.timeZone = timezone

                # Adding windows options
                options = vim.vm.customization.WinOptions()
                options.changeSID = True
                options.deleteAccounts = False
                customspec.options = options
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

        if (self.get_server_by_name(vm_name)):
            raise cfy_exc.NonRecoverableError(
                "We allready have some VM with name: {0}."
                .format(vm_name))

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

        vm = self.get_server_by_name(vm_name)
        ctx.instance.runtime_properties[NETWORKS] = \
            self.get_vm_networks(vm)
        ctx.logger.debug('Updated runtime properties with network information')

        return task.info.result

    def start_server(self, server):
        ctx.logger.debug("Entering server start procedure.")
        task = server.PowerOn()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now running.")

    def shutdown_server_guest(self, server):
        ctx.logger.debug("Entering server shutdown procedure.")
        server.ShutdownGuest()
        ctx.logger.debug("Server is now shut down.")

    def stop_server(self, server):
        ctx.logger.debug("Entering stop server procedure.")
        task = server.PowerOff()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now stopped.")

    def is_server_poweredoff(self, server):
        return server.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.guest.guestState == "running"

    def delete_server(self, server):
        ctx.logger.debug("Entering server delete procedure.")
        if self.is_server_poweredon(server):
            self.stop_server(server)
        task = server.Destroy()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now deleted.")

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
            raise cfy_exc.NonRecoverableError(msg)
        ctx.logger.debug(
            'Looking for datastore with most remaining space from '
            '{datastores}'.format(
                datastores=''.join(
                    [datastore.name for datastore in datastore_list]
                )
            )
        )
        for datastore in datastore_list:
            if datastore._moId not in except_datastores:
                dtstr_free_spc = datastore.info.freeSpace
                if selected_datastore is None:
                    selected_datastore = datastore
                    ctx.logger.debug(
                        'Using first datastore {name} with remaining '
                        '{space}'.format(
                            name=datastore.name,
                            space=datastore.info.freeSpace,
                        )
                    )
                else:
                    selected_dtstr_free_spc = selected_datastore.info.freeSpace
                    ctx.logger.debug(
                        'Checking datastore {name} with remaining '
                        '{space}'.format(
                            name=datastore.name,
                            space=datastore.info.freeSpace,
                        )
                    )
                    if dtstr_free_spc > selected_dtstr_free_spc:
                        selected_datastore = datastore
                        ctx.logger.debug(
                            'Selected this datastore as a better candidate.'
                        )

        if selected_datastore is None:
            msg = "Error during placing VM: no datastore found."
            raise cfy_exc.NonRecoverableError(msg)

        if auto_placement:
            # This should be debug, but left as info until CFY-4867 makes logs
            # more visible
            ctx.logger.info('Using datastore {name}.'
                            .format(name=selected_datastore.name))
            return None, selected_datastore

        # This should be debug, but left as info until CFY-4867 makes logs
        # more visible
        ctx.logger.info('Trying to use datastore {name} for deployment.'
                        .format(name=selected_datastore.name))

        for host_mount in selected_datastore.host:
            host = host_mount.key
            if host.overallStatus != vim.ManagedEntity.Status.red:
                if selected_host is None:
                    selected_host = host
                    ctx.logger.debug(
                        'Using first host {name}'.format(
                            name=host.name,
                        )
                    )
                else:
                    host_memory = host.hardware.memorySize
                    host_memory_used = 0
                    for vm in host.vm:
                        if not vm.summary.config.template:
                            host_memory_used += vm.summary.config.memorySizeMB

                    host_memory_delta = host_memory - host_memory_used
                    selected_host_memory_delta =\
                        selected_host_memory - selected_host_memory_used
                    ctx.logger.debug(
                        'Comparing candidate host {candidate_name} with '
                        'available memory {candidate_memory} to current '
                        'selected host {host} with available memory '
                        '{memory}'.format(
                            candidate_name=host.name,
                            candidate_memory=host_memory_delta,
                            host=selected_host.name,
                            memory=selected_host_memory_delta,
                        )
                    )
                    if host_memory_delta > selected_host_memory_delta:
                        selected_host = host
                        selected_host_memory = host_memory
                        selected_host_memory_used = host_memory_used
            else:
                ctx.logger.warn(
                    'Can not use host {name} for deployment. Status is '
                    'red.'.format(
                        name=selected_datastore.name,
                    )
                )

        if selected_host is None:
            except_datastores.append(selected_datastore._moId)
            ctx.logger.warn(
                'Not using datastore {datastore}. No suitable host '
                'found.'.format(
                    datastore=selected_datastore.name,
                )
            )
            return self.place_vm(auto_placement, except_datastores)

        # This should be debug, but left as info until CFY-4867 makes logs
        # more visible
        ctx.logger.info(
            'Deploying to host {name} on datastore {datastore}'.format(
                name=host.name,
                datastore=selected_datastore.name,
            )
        )
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
        ctx.logger.debug("Server resized with new number of "
                         "CPUs: %s and RAM: %s." % (cpus, memory))

    def get_server_ip(self, vm, network_name):
        ctx.logger.debug(
            'Getting server IP from {network}.'.format(
                network=network_name,
            )
        )

        for network in vm.guest.net:
            if not network.network:
                ctx.logger.warn(
                    'Ignoring device with MAC {mac} as it is not on a '
                    'vSphere network.'.format(
                        mac=network.macAddress,
                    )
                )
                continue
            if (
                network.network and
                network_name.lower() == network.network.lower() and
                len(network.ipAddress) > 0
            ):
                ip_address = get_ip_from_vsphere_nic_ips(network)
                # This should be debug, but left as info until CFY-4867 makes
                # logs more visible
                ctx.logger.info(
                    'Found {ip} from device with MAC {mac}'.format(
                        ip=ip_address,
                        mac=network.macAddress,
                    )
                )
                return ip_address

    def _wait_vm_running(self, task):
        time.sleep(TASK_CHECK_SLEEP)
        self._wait_for_task(task)
        while not task.info.result.guest.guestState == "running"\
                or not task.info.result.guest.net:
            time.sleep(TASK_CHECK_SLEEP)


class NetworkClient(VsphereClient):

    def get_host_list(self, force_refresh=False):
        # Each invocation of this takes up to a few seconds, so try to avoid
        # calling it too frequently by caching
        if hasattr(self, 'host_list') and not force_refresh:
            return self.host_list
        self.host_list = self.get_obj_list([vim.HostSystem])
        return self.host_list

    def delete_port_group(self, name):
        ctx.logger.debug("Deleting port group {name}.".format(
                         name=name))
        for host in self.get_host_list():
            host.configManager.networkSystem.RemovePortGroup(name)
        ctx.logger.debug("Port group {name} was deleted.".format(
                         name=name))

    def get_vswitches(self):
        ctx.logger.debug('Getting list of vswitches')

        # We only want to list vswitches that are on all hosts, as we will try
        # to create port groups on the same vswitch on every host.
        vswitches = set()
        for host in self.get_host_list():
            conf = host.config
            current_host_vswitches = set()
            for vswitch in conf.network.vswitch:
                current_host_vswitches.add(vswitch.name)
            if len(vswitches) == 0:
                vswitches = current_host_vswitches
            else:
                vswitches = vswitches.union(current_host_vswitches)

        ctx.logger.debug('Found vswitches'.format(vswitches=vswitches))
        return vswitches

    def get_dvswitches(self):
        ctx.logger.debug('Getting list of dvswitches')

        # This does not currently address multiple datacenters (indeed,
        # much of this code will probably have issues in such an environment).
        dvswitches = self.get_obj_list([
            vim.dvs.VmwareDistributedVirtualSwitch,
        ])
        dvswitches = [dvswitch.name for dvswitch in dvswitches]

        ctx.logger.debug('Found dvswitches'.format(dvswitches=dvswitches))
        return dvswitches

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Entering create port procedure.")

        vswitches = self.get_vswitches()

        if vswitch_name not in vswitches:
            if len(vswitches) == 0:
                raise cfy_exc.NonRecoverableError(
                    'No valid vswitches found. '
                    'Every physical host in the datacenter must have the '
                    'same named vswitches available when not using '
                    'distributed vswitches.'
                )
            else:
                raise cfy_exc.NonRecoverableError(
                    '{vswitch} was not a valid vswitch name. The valid '
                    'vswitches are: {vswitches}'.format(
                        vswitch=vswitch_name,
                        vswitches=', '.join(vswitches),
                    )
                )

        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            specification = vim.host.PortGroup.Specification()
            specification.name = port_group_name
            specification.vlanId = vlan_id
            specification.vswitchName = vswitch_name
            vswitch = network_system.networkConfig.vswitch[0]
            specification.policy = vswitch.spec.policy
            ctx.logger.debug(
                'Adding port group {group_name} to vSwitch {vswitch_name} on '
                'host {host_name}'.format(
                    group_name=port_group_name,
                    vswitch_name=vswitch_name,
                    host_name=host.name,
                )
            )
            network_system.AddPortGroup(specification)

    def get_port_group_by_name(self, name):
        ctx.logger.debug("Getting port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    ctx.logger.debug("Port group(s) info: \n%s." %
                                     "".join("%s: %s" % item
                                             for item in
                                             vars(port_group).items()))
                    result.append(port_group)
        return result

    def create_dv_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Creating dv port group.")

        dvswitches = self.get_dvswitches()

        if vswitch_name not in dvswitches:
            if len(dvswitches) == 0:
                raise cfy_exc.NonRecoverableError(
                    'No valid dvswitches found. '
                    'A distributed virtual switch must exist for distributed '
                    'port groups to be used.'
                )
            else:
                raise cfy_exc.NonRecoverableError(
                    '{dvswitch} was not a valid dvswitch name. The valid '
                    'dvswitches are: {dvswitches}'.format(
                        dvswitch=vswitch_name,
                        dvswitches=', '.join(dvswitches),
                    )
                )

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
        ctx.logger.debug(
            'Adding distributed port group {group_name} to dvSwitch '
            '{dvswitch_name}'.format(
                group_name=port_group_name,
                dvswitch_name=vswitch_name,
            )
        )
        task = dvswitch.AddPortgroup(specification)
        self._wait_for_task(task)
        ctx.logger.debug("Port created.")

    def delete_dv_port_group(self, name):
        ctx.logger.debug("Deleting dv port group {name}.".format(
                         name=name))
        dv_port_group = self.get_dv_port_group(name)
        task = dv_port_group.Destroy()
        self._wait_for_task(task)
        ctx.logger.debug("Port deleted.")

    def get_dv_port_group(self, name):
        dv_port_group = self._get_obj_by_name(
            [vim.dvs.DistributedVirtualPortgroup],
            name)
        return dv_port_group


class StorageClient(VsphereClient):

    def create_storage(self, vm_id, storage_size):
        ctx.logger.debug("Entering create storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage:'
                ' invalid VM state - \'suspended\''
            )

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
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage:'
                ' Invalid VMDK name - \'{0}\''.format(vm_disk_filename_cur)
            )

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
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage: '
                'SCSI controller cannot be found or is present more than '
                'once.'
            )

        controller_key = controller.key

        # Set new unit number (7 cannot be used, and limit is 15)
        unit_number = None
        vm_vdisk_number = len(controller.device)
        if vm_vdisk_number < 7:
            unit_number = vm_vdisk_number
        elif vm_vdisk_number == 15:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage: one SCSI controller '
                'cannot have more than 15 virtual disks.'
            )
        else:
            unit_number = vm_vdisk_number + 1

        virtual_device_spec.device.backing.fileName = vm_disk_filename
        virtual_device_spec.device.controllerKey = controller_key
        virtual_device_spec.device.unitNumber = unit_number
        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.debug("Task info: \n%s." % prepare_for_log(vars(task)))
        self._wait_for_task(task)

        # Get the SCSI bus and unit IDs
        scsi_controllers = []
        disks = []
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualSCSIController):
                scsi_controllers.append(device)
            elif isinstance(device, vim.vm.device.VirtualDisk):
                disks.append(device)
        # Find the disk we just created
        for disk in disks:
            if disk.backing.fileName == vm_disk_filename:
                unit = disk.unitNumber
                bus_id = None
                for controller in scsi_controllers:
                    if controller.key == disk.controllerKey:
                        bus_id = controller.busNumber
                        break
                # We found the right disk, we can't do any better than this
                break
        if bus_id is None:
            raise cfy_exc.NonRecoverableError(
                'Could not find SCSI bus ID for disk with filename: '
                '{file}'.format(file=vm_disk_filename)
            )
        else:
            # Give the SCSI ID in the usual format, e.g. 0:1
            scsi_id = ':'.join((str(bus_id), str(unit)))

        return vm_disk_filename, scsi_id

    def delete_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
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
            raise cfy_exc.NonRecoverableError(
                'Error during trying to delete storage: storage not found')

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.Reconfigure(spec=config_spec)
        ctx.logger.debug("Task info: \n%s." % prepare_for_log(vars(task)))
        self._wait_for_task(task)

    def get_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if vm:
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk)\
                        and device.backing.fileName == storage_file_name:
                    ctx.logger.debug(
                        "Device info: \n%s." % prepare_for_log(vars(device))
                    )
                    return device
        return None

    def resize_storage(self, vm_id, storage_filename, storage_size):
        ctx.logger.debug("Entering resize storage procedure.")
        vm = self._get_obj_by_id([vim.VirtualMachine], vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                'Error during trying to resize storage: invalid VM state'
                ' - \'suspended\'')

        disk_to_resize = None
        devices = vm.config.hardware.device
        for device in devices:
            if (isinstance(device, vim.vm.device.VirtualDisk) and
                    device.backing.fileName == storage_filename):
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
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        self._wait_for_task(task)
        ctx.logger.debug("Storage resized to a new size %s." % storage_size)


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
