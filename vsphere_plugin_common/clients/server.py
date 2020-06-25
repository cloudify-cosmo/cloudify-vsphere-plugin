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
import time
from netaddr import IPNetwork
from pyVmomi import vim, vmodl

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

# This package imports
from . import VsphereClient
from ..constants import (
    IP,
    TASK_CHECK_SLEEP,
    VSPHERE_SERVER_ID,
    VSPHERE_SERVER_CLUSTER_NAME,
    VSPHERE_SERVER_HYPERVISOR_HOSTNAME
)
from .._compat import text_type
from ..utils import logger, prepare_for_log


def get_ip_from_vsphere_nic_ips(nic, ignore_local=True):
    for ip in nic.ipAddress:
        # Check if the IP is routable.
        ipv4_unroutable = ip.startswith('169.254.')
        ipv6_unroutable = ip.lower().startswith('fe80::')
        unroutable = ipv4_unroutable or ipv6_unroutable
        # If we want to ignore local,
        # and the IP falls under one of the local unroutable IP classes.
        if ignore_local and unroutable:
            # This is a locally assigned IPv4 or IPv6 address and thus we
            # will assume it is not routable
            logger().debug(
                'Found locally assigned IP {ip}. Skipping.'.format(ip=ip))
            continue
        else:
            return ip
    return


class ServerClient(VsphereClient):

    def _get_port_group_names(self):
        all_port_groups = self._get_networks()

        port_groups = []
        distributed_port_groups = []

        for port_group in all_port_groups:
            if self._port_group_is_distributed(port_group):
                distributed_port_groups.append(port_group.name.lower())
            else:
                port_groups.append(port_group.name.lower())

        return port_groups, distributed_port_groups

    def _validate_allowed(self, thing_type, allowed_things, existing_things):
        """
            Validate that an allowed hosts, clusters, or datastores list is
            valid.
        """
        self._logger.debug(
            'Checking allowed {thing}s list.'.format(thing=thing_type)
        )
        not_things = set(allowed_things).difference(set(existing_things))
        if len(not_things) == len(allowed_things):
            return (
                'No allowed {thing}s exist. Allowed {thing}(s): {allow}. '
                'Existing {thing}(s): {exist}.'.format(
                    allow=', '.join(allowed_things),
                    exist=', '.join(existing_things),
                    thing=thing_type,
                )
            )
        elif len(not_things) > 0:
            self._logger.warn(
                'One or more specified allowed {thing}s do not exist: '
                '{not_things}'.format(
                    thing=thing_type,
                    not_things=', '.join(not_things),
                )
            )

    def _validate_inputs(self,
                         allowed_hosts,
                         allowed_clusters,
                         allowed_datastores,
                         template_name,
                         datacenter_name,
                         resource_pool_name,
                         networks):
        """
            Make sure we can actually continue with the inputs given.
            If we can't, we want to report all of the issues at once.
        """
        self._logger.debug('Validating inputs for this platform.')
        issues = []

        hosts = self._get_hosts()
        host_names = [host.name for host in hosts]

        if allowed_hosts:
            error = self._validate_allowed('host', allowed_hosts, host_names)
            if error:
                issues.append(error)

        if allowed_clusters:
            cluster_list = self._get_clusters()
            cluster_names = [cluster.name for cluster in cluster_list]
            error = self._validate_allowed(
                'cluster',
                allowed_clusters,
                cluster_names,
            )
            if error:
                issues.append(error)

        if allowed_datastores:
            datastore_list = self._get_datastores()
            datastore_names = [datastore.name for datastore in datastore_list]
            error = self._validate_allowed(
                'datastore',
                allowed_datastores,
                datastore_names,
            )
            if error:
                issues.append(error)

        self._logger.debug('Checking template exists.')
        template_vm = self._get_obj_by_name(vim.VirtualMachine,
                                            template_name)
        if template_vm is None:
            issues.append("VM template {0} could not be found.".format(
                template_name
            ))

        self._logger.debug('Checking resource pool exists.')
        resource_pool = self._get_obj_by_name(
            vim.ResourcePool,
            resource_pool_name,
        )
        if resource_pool is None:
            issues.append("Resource pool {0} could not be found.".format(
                resource_pool_name,
            ))

        self._logger.debug('Checking datacenter exists.')
        datacenter = self._get_obj_by_name(vim.Datacenter,
                                           datacenter_name)
        if datacenter is None:
            issues.append("Datacenter {0} could not be found.".format(
                datacenter_name
            ))

        self._logger.debug(
            'Checking networks exist.'
        )
        port_groups, distributed_port_groups = self._get_port_group_names()
        for network in networks:
            try:
                network_name = self._get_connected_network_name(network)
            except NonRecoverableError as err:
                issues.append(text_type(err))
                continue
            network_name = self._get_normalised_name(network_name)
            switch_distributed = network['switch_distributed']

            list_distributed_networks = False
            list_networks = False
            # Check network exists and provide helpful message if it doesn't
            # Note that we special-case alerting if switch_distributed appears
            # to be set incorrectly.
            # Use lowercase name for comparison as vSphere appears to be case
            # insensitive for this.
            if switch_distributed:
                error_message = \
                    'Distributed network "{name}" ' \
                    'not present on vSphere.'.format(name=network_name)
                if network_name not in distributed_port_groups:
                    if network_name in port_groups:
                        issues.append(
                            error_message + ' However, this is present as a '
                            'standard network. You may need to set the '
                            'switch_distributed setting for this network to '
                            'false.'
                        )
                    else:
                        issues.append(error_message)
                        list_distributed_networks = True
            else:
                error_message = \
                    'Network "{name}" not present on vSphere.'.format(
                        name=network_name)
                if network_name not in port_groups:
                    if network_name in distributed_port_groups:
                        issues.append(
                            error_message + ' However, this is present as a '
                            'distributed network. You may need to set the '
                            'switch_distributed setting for this network to '
                            'true.'
                        )
                    else:
                        issues.append(error_message)
                        list_networks = True

            if list_distributed_networks:
                issues.append(
                    ' Available distributed networks '
                    'are: {nets}.'.format(
                        nets=', '.join(distributed_port_groups)))
            if list_networks:
                issues.append(
                    ' Available networks are: '
                    '{nets}.'.format(nets=', '.join(port_groups)))

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise NonRecoverableError(message)

    def _validate_windows_properties(
            self,
            custom_sysprep,
            windows_organization,
            windows_password):
        issues = []

        if windows_password == '':
            # Avoid falsey comparison on blank password
            windows_password = True
        if windows_password == '':
            # Avoid falsey comparison on blank password
            windows_password = True
        if custom_sysprep is not None:
            if windows_password:
                issues.append(
                    'custom_sysprep answers data has been provided, but a '
                    'windows_password was supplied. If using custom sysprep, '
                    'no other windows settings are usable.'
                )
        elif not windows_password and custom_sysprep is None:
            if not windows_password:
                issues.append(
                    'Windows password must be set when a custom sysprep is '
                    'not being performed. Please supply a windows_password '
                    'using either properties.windows_password or '
                    'properties.agent_config.password'
                )

        if len(windows_organization) == 0:
            issues.append('windows_organization property must not be blank')
        if len(windows_organization) > 64:
            issues.append(
                'windows_organization property must be 64 characters or less')

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise NonRecoverableError(message)

    def _add_network(self, network, datacenter):
        network_name = network['name']
        normalised_network_name = self._get_normalised_name(network_name)
        switch_distributed = network['switch_distributed']
        mac_address = network.get('mac_address')

        use_dhcp = network['use_dhcp']
        if switch_distributed:
            for port_group in datacenter.obj.network:
                # Make sure that we are comparing normalised network names.
                normalised_port_group_name = self._get_normalised_name(
                    port_group.name
                )
                if normalised_port_group_name == normalised_network_name:
                    network_obj = \
                        self._convert_vmware_port_group_to_cloudify(port_group)
                    break
            else:
                self._logger.warning(
                    "Network {name} couldn't be found.  Only found {networks}."
                    .format(name=network_name, networks=text_type([
                        net.name for net in datacenter.obj.network])))
                network_obj = None
        else:
            network_obj = self._get_obj_by_name(
                vim.Network,
                network_name,
            )
        if network_obj is None:
            raise NonRecoverableError(
                'Network {0} could not be found'.format(network_name))
        nicspec = vim.vm.device.VirtualDeviceSpec()
        # Info level as this is something that was requested in the
        # blueprint
        self._logger.info(
            'Adding network interface on {name}'.format(
                name=network_name))
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
            nicspec.device.backing.network = network_obj.obj
            nicspec.device.backing.deviceName = network_name
        if mac_address:
            nicspec.device.macAddress = mac_address

        if use_dhcp:
            guest_map = vim.vm.customization.AdapterMapping()
            guest_map.adapter = vim.vm.customization.IPSettings()
            guest_map.adapter.ip = vim.vm.customization.DhcpIpGenerator()
        else:
            nw = IPNetwork(network["network"])
            guest_map = vim.vm.customization.AdapterMapping()
            guest_map.adapter = vim.vm.customization.IPSettings()
            guest_map.adapter.ip = vim.vm.customization.FixedIp()
            guest_map.adapter.ip.ipAddress = network[IP]
            guest_map.adapter.gateway = network["gateway"]
            guest_map.adapter.subnetMask = text_type(nw.netmask)
        return nicspec, guest_map

    def _get_nic_keys_for_remove(self, server):
        # get nics keys in template before our changes,
        # we must use keys instead of mac addresses, as macs will be changed
        # after VM create
        keys = []
        for device in server.config.hardware.device:
            # delete network interface
            if hasattr(device, 'macAddress'):
                keys.append(device.key)
        return keys

    def remove_nic_keys(self, server, keys):
        self._logger.debug(
            'Removing network adapters {keys} from vm. '
            .format(keys=text_type(keys)))
        # remove nics by key
        for key in keys:
            devices = []
            for device in server.config.hardware.device:
                # delete network interface
                if key == device.key:
                    nicspec = vim.vm.device.VirtualDeviceSpec()
                    nicspec.device = device
                    self._logger.debug(
                        'Removing network adapter {key} from vm. '
                        .format(key=device.key))
                    nicspec.operation = \
                        vim.vm.device.VirtualDeviceSpec.Operation.remove
                    devices.append(nicspec)
            if devices:
                # apply changes
                spec = vim.vm.ConfigSpec()
                spec.deviceChange = devices
                task = server.obj.ReconfigVM_Task(spec=spec)
                self._wait_for_task(task)
                # update server object
                server = self._get_obj_by_id(
                    vim.VirtualMachine,
                    server.obj._moId,
                    use_cache=False,
                )

    def _update_vm(self, server, cdrom_image=None, remove_networks=False):
        # update vm with attach cdrom image and remove network adapters
        devices = []
        ide_controller = None
        cdrom_attached = False
        for device in server.config.hardware.device:
            # delete network interface
            if remove_networks and hasattr(device, 'macAddress'):
                nicspec = vim.vm.device.VirtualDeviceSpec()
                nicspec.device = device
                self._logger.warn(
                    'Removing network adapter {mac} from template. '
                    'Template should have no attached adapters.'
                    .format(mac=device.macAddress))
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.remove
                devices.append(nicspec)
            # remove cdrom when we have cloudinit
            elif isinstance(device, vim.vm.device.VirtualCdrom) and \
                    cdrom_image:
                self._logger.warn(
                    'Edit cdrom from template. '
                    'Template should have no inserted cdroms.')
                cdrom_attached = True
                # skip if cdrom is already attached
                if isinstance(
                    device.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo
                ):
                    if text_type(
                            device.backing.fileName) == text_type(cdrom_image):
                        self._logger.info(
                            "Specified CD image is already mounted.")
                        continue
                cdrom = vim.vm.device.VirtualDeviceSpec()
                cdrom.device = device
                device.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(
                    fileName=cdrom_image)
                cdrom.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.edit
                connectable = vim.vm.device.VirtualDevice.ConnectInfo()
                connectable.allowGuestControl = True
                connectable.startConnected = True
                device.connectable = connectable
                devices.append(cdrom)
                ide_controller = device.controllerKey
            # ide controller
            elif isinstance(device, vim.vm.device.VirtualIDEController):
                # skip fully attached controllers
                if len(device.device) < 2:
                    ide_controller = device.key

        # attach cdrom
        if cdrom_image and not cdrom_attached:
            if not ide_controller:
                raise NonRecoverableError(
                    'IDE controller is required for attach cloudinit cdrom.')

            cdrom_device = vim.vm.device.VirtualDeviceSpec()
            cdrom_device.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.add
            connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            connectable.allowGuestControl = True
            connectable.startConnected = True

            cdrom = vim.vm.device.VirtualCdrom()
            cdrom.controllerKey = ide_controller
            cdrom.key = -1
            cdrom.connectable = connectable
            cdrom.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(
                fileName=cdrom_image)
            cdrom_device.device = cdrom
            devices.append(cdrom_device)
        return devices

    def update_server(self, server, cdrom_image=None, extra_config=None):
        # Attrach cdrom image to vm without change networks list
        devices_changes = self._update_vm(server, cdrom_image=cdrom_image,
                                          remove_networks=False)
        if devices_changes or extra_config:
            spec = vim.vm.ConfigSpec()
            # changed devices
            if devices_changes:
                spec.deviceChange = devices_changes
            # add extra config
            if extra_config and isinstance(extra_config, dict):
                self._logger.debug('Extra config: {config}'
                                   .format(config=text_type(extra_config)))
                for k in extra_config:
                    spec.extraConfig.append(
                        vim.option.OptionValue(key=k, value=extra_config[k]))
            task = server.obj.ReconfigVM_Task(spec=spec)
            self._wait_for_task(task)

    def _get_virtual_hardware_version(self, vm):
        # See https://kb.vmware.com/s/article/1003746 for documentation on VM
        # hardware versions and ESXi version compatibility.
        return int(vm.config.version.lstrip("vmx-"))

    def create_server(
            self,
            auto_placement,
            cpus,
            datacenter_name,
            memory,
            networks,
            resource_pool_name,
            template_name,
            vm_name,
            windows_password,
            windows_organization,
            windows_timezone,
            agent_config,
            custom_sysprep,
            os_type='linux',
            domain=None,
            dns_servers=None,
            allowed_hosts=None,
            allowed_clusters=None,
            allowed_datastores=None,
            cdrom_image=None,
            vm_folder=None,
            extra_config=None,
            enable_start_vm=True,
            postpone_delete_networks=False):

        self._logger.debug(
            "Entering create_server with parameters %s"
            % prepare_for_log(locals()))

        self._validate_inputs(
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
            allowed_datastores=allowed_datastores,
            template_name=template_name,
            networks=networks,
            resource_pool_name=resource_pool_name,
            datacenter_name=datacenter_name
        )

        # If cpus and memory are not specified, take values from the template.
        template_vm = self._get_obj_by_name(vim.VirtualMachine, template_name)
        if not cpus:
            cpus = template_vm.config.hardware.numCPU

        if not memory:
            memory = template_vm.config.hardware.memoryMB

        # Correct the network name for all networks from relationships
        for network in networks:
            network['name'] = self._get_connected_network_name(network)

        datacenter = self._get_obj_by_name(vim.Datacenter, datacenter_name)

        candidate_hosts = self.find_candidate_hosts(
            datacenter=datacenter,
            resource_pool=resource_pool_name,
            vm_cpus=cpus,
            vm_memory=memory,
            vm_networks=networks,
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
        )

        host, datastore = self.select_host_and_datastore(
            candidate_hosts=candidate_hosts,
            vm_memory=memory,
            template=template_vm,
            allowed_datastores=allowed_datastores,
        )
        ctx.instance.runtime_properties[
            VSPHERE_SERVER_HYPERVISOR_HOSTNAME] = host.name
        ctx.instance.runtime_properties[
            VSPHERE_SERVER_CLUSTER_NAME] = host.parent.name
        self._logger.debug(
            'Using host {host} and datastore {ds} for deployment.'.format(
                host=host.name,
                ds=datastore.name,
            )
        )

        adaptermaps = []

        resource_pool = self.get_resource_pool(
            host=host, resource_pool_name=resource_pool_name)

        if not vm_folder:
            destfolder = datacenter.vmFolder
        else:
            folder = self._get_obj_by_name(vim.Folder, vm_folder)
            if not folder:
                raise NonRecoverableError(
                    'Could not use vm_folder "{name}" as no '
                    'vm folder by that name exists!'.format(
                        name=vm_folder,
                    )
                )
            destfolder = folder.obj

        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore.obj
        relospec.pool = resource_pool.obj
        if not auto_placement:
            self._logger.warn(
                'Disabled autoplacement is not recomended for a cluster.'
            )
            relospec.host = host.obj

        # Get list of NIC MAC addresses for removal
        if postpone_delete_networks and not enable_start_vm:
            keys_for_remove = []
            keys_for_remove = self._get_nic_keys_for_remove(template_vm)
            ctx.instance.runtime_properties[
                '_keys_for_remove'] = keys_for_remove
            ctx.instance.runtime_properties.dirty = True
            ctx.instance.update()

        if postpone_delete_networks and enable_start_vm:
            self._logger.info("Using postpone_delete_networks with "
                              "enable_start_vm is unsupported.")

        # attach cdrom image and remove all networks
        devices = self._update_vm(template_vm,
                                  cdrom_image=cdrom_image,
                                  remove_networks=not postpone_delete_networks)

        port_groups, distributed_port_groups = self._get_port_group_names()

        for network in networks:
            nicspec, guest_map = self._add_network(network, datacenter)
            devices.append(nicspec)
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
        clonespec.powerOn = enable_start_vm
        clonespec.template = False

        # add extra config
        if extra_config and isinstance(extra_config, dict):
            self._logger.debug('Extra config: {config}'
                               .format(config=text_type(extra_config)))
            for k in extra_config:
                clonespec.extraConfig.append(
                    vim.option.OptionValue(key=k, value=extra_config[k]))

        if adaptermaps:
            self._logger.debug(
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
                if not windows_password:
                    if not agent_config:
                        agent_config = {}
                    windows_password = agent_config.get('password')

                self._validate_windows_properties(
                    custom_sysprep,
                    windows_organization,
                    windows_password)

                if custom_sysprep is not None:
                    ident = vim.vm.customization.SysprepText()
                    ident.value = custom_sysprep
                else:
                    # We use GMT without daylight savings if no timezone is
                    # supplied, as this is as close to UTC as we can do
                    if not windows_timezone:
                        windows_timezone = 90

                    ident = vim.vm.customization.Sysprep()
                    ident.userData = vim.vm.customization.UserData()
                    ident.guiUnattended = vim.vm.customization.GuiUnattended()
                    ident.identification = (
                        vim.vm.customization.Identification()
                    )

                    # Configure userData
                    ident.userData.computerName = (
                        vim.vm.customization.FixedName()
                    )
                    ident.userData.computerName.name = vm_name
                    # Without these vars, customization is silently skipped
                    # but deployment 'succeeds'
                    ident.userData.fullName = vm_name
                    ident.userData.orgName = windows_organization
                    ident.userData.productId = ""

                    # Configure guiUnattended
                    ident.guiUnattended.autoLogon = False
                    ident.guiUnattended.password = (
                        vim.vm.customization.Password()
                    )
                    ident.guiUnattended.password.plainText = True
                    ident.guiUnattended.password.value = windows_password
                    ident.guiUnattended.timeZone = windows_timezone

                # Adding windows options
                options = vim.vm.customization.WinOptions()
                options.changeSID = True
                options.deleteAccounts = False
                customspec.options = options
            elif os_type == 'solaris':
                ident = None
                self._logger.info(
                    'Customization of the Solaris OS is unsupported by '
                    ' vSphere. Guest additions are required/supported.')
            else:
                ident = None
                self._logger.info(
                    'os_type {os_type} was specified, but only "windows", '
                    '"solaris" and "linux" are supported. Customization is '
                    'unsupported.'
                    .format(os_type=os_type)
                )

            if ident:
                customspec.identity = ident

                globalip = vim.vm.customization.GlobalIPSettings()
                if dns_servers:
                    globalip.dnsServerList = dns_servers
                customspec.globalIPSettings = globalip

                clonespec.customization = customspec
        self._logger.info(
            'Cloning {server} from {template}.'.format(
                server=vm_name, template=template_name))
        self._logger.debug('Cloning with clonespec: {spec}'
                           .format(spec=text_type(clonespec)))
        task = template_vm.obj.Clone(folder=destfolder,
                                     name=vm_name,
                                     spec=clonespec)
        try:
            self._logger.debug(
                "Task info: {task}".format(task=text_type(task)))
            # wait for task finish
            self._wait_for_task(task, resource_id=VSPHERE_SERVER_ID)

            ctx.instance.runtime_properties['name'] = vm_name
            ctx.instance.runtime_properties.dirty = True
            ctx.instance.update()

            if enable_start_vm:
                self._logger.info('VM created in running state')
                while not self._wait_vm_running(
                    task.info.result, adaptermaps, os_type == "other"
                ):
                    time.sleep(TASK_CHECK_SLEEP)
            else:
                self._logger.info('VM created in stopped state')
        except task.info.error:
            raise NonRecoverableError(
                "Error during executing VM creation task. "
                "VM name: \'{0}\'.".format(vm_name))

        # VM object created. Now perform final post-creation tasks
        vm = self._get_obj_by_id(
            vim.VirtualMachine,
            task.info.result._moId,
            use_cache=False,
        )

        return vm

    def upgrade_server(self, server, minimal_vm_version):
        self._logger.info('VM version: vmx-{old}/vmx-{new}'.format(
            old=self._get_virtual_hardware_version(server.obj),
            new=minimal_vm_version))
        if self._get_virtual_hardware_version(server.obj) < minimal_vm_version:
            if self.is_server_poweredon(server):
                self._logger.info(
                    "Use VM hardware update with `enable_start_vm` is "
                    "unsupported.")
            else:
                self._logger.info("Going to update VM hardware version.")
                task = server.obj.UpgradeVM_Task(
                    "vmx-{version}".format(version=minimal_vm_version))
                self._wait_for_task(task)

    def suspend_server(self, server, max_wait_time=30):
        if self.is_server_suspended(server.obj):
            self._logger.info("Server '{}' already suspended."
                              .format(server.name))
            return
        if self.is_server_poweredoff(server):
            self._logger.info("Server '{}' is powered off so will not be "
                              "suspended.".format(server.name))
            return
        self._logger.debug("Entering server suspend procedure.")
        task = server.obj.Suspend()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server is suspended.")

    def start_server(self, server, max_wait_time=30):
        if self.is_server_poweredon(server):
            self._logger.info("Server '{}' already running"
                              .format(server.name))
            return
        self._logger.debug("Entering server start procedure.")
        task = server.obj.PowerOn()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server is now running.")

    def shutdown_server_guest(self, server, max_wait_time=30):
        if self.is_server_poweredoff(server):
            self._logger.info("Server '{}' already stopped"
                              .format(server.name))
            return
        self._logger.debug("Entering server shutdown procedure.")
        task = server.obj.ShutdownGuest()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server is now shut down.")

    def stop_server(self, server, max_wait_time=30):
        if self.is_server_poweredoff(server):
            self._logger.info("Server '{}' already stopped"
                              .format(server.name))
            return
        self._logger.debug("Entering stop server procedure.")
        task = server.obj.PowerOff()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server is now stopped.")

    def backup_server(
        self, server, snapshot_name, description, max_wait_time=30
    ):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
            if snapshot:
                raise NonRecoverableError(
                    "Snapshot {snapshot_name} already exists."
                    .format(snapshot_name=snapshot_name,))

        task = server.obj.CreateSnapshot(
            snapshot_name, description=description,
            memory=False, quiesce=False)
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)

    def get_snapshot_by_name(self, snapshots, snapshot_name):
        for snapshot in snapshots:
            if snapshot.name == snapshot_name:
                return snapshot
            else:
                subsnapshot = self.get_snapshot_by_name(
                    snapshot.childSnapshotList, snapshot_name)
                if subsnapshot:
                    return subsnapshot
        return False

    def restore_server(self,
                       server,
                       snapshot_name,
                       max_wait_time=30):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
        else:
            snapshot = None
        if not snapshot:
            raise NonRecoverableError(
                "No snapshots found with name: {snapshot_name}."
                .format(snapshot_name=snapshot_name,))

        task = snapshot.snapshot.RevertToSnapshot_Task()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)

    def remove_backup(self, server, snapshot_name, max_wait_time=30):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
        else:
            snapshot = None
        if not snapshot:
            raise NonRecoverableError(
                "No snapshots found with name: {snapshot_name}."
                .format(snapshot_name=snapshot_name,))

        if snapshot.childSnapshotList:
            subsnapshots = [snap.name for snap in snapshot.childSnapshotList]
            raise NonRecoverableError(
                "Sub snapshots {subsnapshots} found for {snapshot_name}. "
                "You should remove subsnaphots before remove current."
                .format(snapshot_name=snapshot_name,
                        subsnapshots=text_type(subsnapshots)))

        task = snapshot.snapshot.RemoveSnapshot_Task(True)
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)

    def reset_server(self, server, max_wait_time=30):
        if self.is_server_poweredoff(server):
            self._logger.info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server,
                                     max_wait_time=max_wait_time)
        self._logger.debug("Entering stop server procedure.")
        task = server.obj.Reset()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server has been reset")

    def reboot_server(self, server, max_wait_time=30):
        if self.is_server_poweredoff(server):
            self._logger.info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server,
                                     max_wait_time=max_wait_time)
        self._logger.debug("Entering reboot server procedure.")
        task = server.obj.RebootGuest()
        self._wait_for_task(task,
                            max_wait_time=max_wait_time)
        self._logger.debug("Server has been rebooted")

    def is_server_poweredoff(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.obj.guest.guestState == "running"

    def delete_server(self, server):
        self._logger.debug("Entering server delete procedure.")
        if self.is_server_poweredon(server):
            self.stop_server(server)
        task = server.obj.Destroy()
        self._wait_for_task(task)
        self._logger.debug("Server is now deleted.")

    def get_server_by_name(self, name):
        return self._get_obj_by_name(vim.VirtualMachine, name)

    def get_server_by_id(self, id):
        return self._get_obj_by_id(vim.VirtualMachine, id)

    def find_candidate_hosts(self,
                             resource_pool,
                             vm_cpus,
                             vm_memory,
                             vm_networks,
                             allowed_hosts=None,
                             allowed_clusters=None,
                             datacenter=None):
        self._logger.debug('Finding suitable hosts for deployment.')

        # Find the hosts in the correct datacenter
        if datacenter:
            hosts = self._get_hosts_in_tree(datacenter.obj.hostFolder)
        else:
            hosts = self._get_hosts()

        host_names = [host.name for host in hosts]
        self._logger.debug(
            'Found hosts: {hosts}'.format(
                hosts=', '.join(host_names),
            )
        )

        if allowed_hosts:
            hosts = [host for host in hosts if host.name in allowed_hosts]
            self._logger.debug(
                'Filtered list of hosts to be considered: {hosts}'.format(
                    hosts=', '.join([host.name for host in hosts]),
                )
            )

        if allowed_clusters:
            cluster_list = self._get_clusters()
            cluster_names = [cluster.name for cluster in cluster_list]
            valid_clusters = set(allowed_clusters).union(set(cluster_names))
            self._logger.debug(
                'Only hosts on the following clusters will be used: '
                '{clusters}'.format(
                    clusters=', '.join(valid_clusters),
                )
            )

        candidate_hosts = []
        for host in hosts:
            if not self.host_is_usable(host):
                self._logger.warn(
                    'Host {host} not usable due to health status.'.format(
                        host=host.name,
                    )
                )
                continue

            if allowed_clusters:
                cluster = self.get_host_cluster_membership(host)
                if cluster not in allowed_clusters:
                    if cluster:
                        self._logger.warn(
                            'Host {host} is in cluster {cluster}, '
                            'which is not an allowed cluster.'.format(
                                host=host.name,
                                cluster=cluster,
                            )
                        )
                    else:
                        self._logger.warn(
                            'Host {host} is not in a cluster, '
                            'and allowed clusters have been set.'.format(
                                host=host.name,
                            )
                        )
                    continue

            memory_weight = self.host_memory_usage_ratio(host, vm_memory)

            if memory_weight < 0:
                self._logger.warn(
                    'Host {host} will not have enough free memory if all VMs '
                    'are powered on.'.format(
                        host=host.name,
                    )
                )

            resource_pools = self.get_host_resource_pools(host)
            resource_pools = [pool.name for pool in resource_pools]
            if resource_pool not in resource_pools:
                self._logger.warn(
                    'Host {host} does not have resource pool {rp}.'.format(
                        host=host.name,
                        rp=resource_pool,
                    )
                )
                continue

            host_nets = set([
                (
                    self._get_normalised_name(network['name']),
                    network['switch_distributed'],
                )
                for network in self.get_host_networks(host)
            ])
            vm_nets = set([
                (
                    self._get_normalised_name(network['name']),
                    network['switch_distributed'],
                )
                for network in vm_networks
            ])

            nets_not_on_host = vm_nets.difference(host_nets)

            if nets_not_on_host:
                message = 'Host {host} does not have all required networks. '

                missing_standard_nets = ', '.join([
                    net[0] for net in nets_not_on_host
                    if not net[1]
                ])
                missing_distributed_nets = ', '.join([
                    net[0] for net in nets_not_on_host
                    if net[1]
                ])

                if missing_standard_nets:
                    message += 'Missing standard networks: {nets}. '

                if missing_distributed_nets:
                    message += 'Missing distributed networks: {dnets}. '

                self._logger.warn(
                    message.format(
                        host=host.name,
                        nets=missing_standard_nets,
                        dnets=missing_distributed_nets,
                    )
                )
                continue

            self._logger.debug(
                'Host {host} is a candidate for deployment.'.format(
                    host=host.name,
                )
            )
            candidate_hosts.append((
                host,
                self.host_cpu_thread_usage_ratio(host, vm_cpus),
                memory_weight,
            ))

        # Sort hosts based on the best processor ratio after deployment
        if candidate_hosts:
            self._logger.debug(
                'Host CPU ratios: {ratios}'.format(
                    ratios=', '.join([
                        '{hostname}: {ratio} {mem_ratio}'.format(
                            hostname=c[0].name,
                            ratio=c[1],
                            mem_ratio=c[2],
                        ) for c in candidate_hosts
                    ])
                )
            )
        candidate_hosts.sort(
            reverse=True,
            key=lambda host_rating: host_rating[1] * host_rating[2]
            # If more ratios are added, take care that they are proper ratios
            # (i.e. > 0), because memory ([2]) isn't, and 2 negatives would
            # cause badly ordered candidates.
        )

        if candidate_hosts:
            return candidate_hosts
        else:
            message = "No healthy hosts could be found with resource pool " \
                      "{pool}, and all required networks.".format(
                          pool=resource_pool)

            if allowed_hosts:
                message += " Only these hosts were allowed: {hosts}".format(
                    hosts=', '.join(allowed_hosts)
                )
            if allowed_clusters:
                message += (
                    " Only hosts in these clusters were allowed: {clusters}"
                ).format(
                    clusters=', '.join(allowed_clusters)
                )

            raise NonRecoverableError(message)

    def get_resource_pool(self, host, resource_pool_name):
        """
            Get the correct resource pool object from the given host.
        """
        resource_pools = self.get_host_resource_pools(host)
        for resource_pool in resource_pools:
            if resource_pool.name == resource_pool_name:
                return resource_pool
        # If we get here, we somehow selected a host without the right
        # resource pool. This should not be able to happen.
        raise NonRecoverableError(
            'Resource pool {rp} not found on host {host}. '
            'Pools found were: {pools}'.format(
                rp=resource_pool_name,
                host=host.name,
                pools=', '.join([p.name for p in resource_pools]),
            )
        )

    def select_host_and_datastore(self,
                                  candidate_hosts,
                                  vm_memory,
                                  template,
                                  allowed_datastores=None):
        """
            Select which host and datastore to use.
            This will assume that the hosts are sorted from most desirable to
            least desirable.
        """
        self._logger.debug('Selecting best host and datastore.')

        best_host = None
        best_datastore = None
        best_datastore_weighting = None

        if allowed_datastores:
            datastore_list = self._get_datastores()
            datastore_names = [datastore.name for datastore in datastore_list]

            valid_datastores = set(allowed_datastores).union(
                set(datastore_names))
            self._logger.debug(
                'Only the following datastores will be used: '
                '{datastores}'.format(
                    datastores=', '.join(valid_datastores),
                )
            )

        for host in candidate_hosts:
            host = host[0]
            self._logger.debug('Considering host {host}'.format(
                host=host.name))

            datastores = host.datastore
            self._logger.debug(
                'Host {host} has datastores: {ds}'.format(
                    host=host.name,
                    ds=', '.join([ds.name for ds in datastores]),
                )
            )
            if allowed_datastores:
                self._logger.debug(
                    'Checking only allowed datastores: {allow}'.format(
                        allow=', '.join(allowed_datastores),
                    )
                )

                datastores = [
                    ds for ds in datastores
                    if ds.name in allowed_datastores
                ]

                if len(datastores) == 0:
                    self._logger.warn(
                        'Host {host} had no allowed datastores.'.format(
                            host=host.name))
                    continue

            self._logger.debug(
                'Filtering for healthy datastores on host {host}'.format(
                    host=host.name,
                )
            )

            healthy_datastores = []
            for datastore in datastores:
                if self.datastore_is_usable(datastore):
                    self._logger.debug(
                        'Datastore {ds} on host {host} is healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )
                    healthy_datastores.append(datastore)
                else:
                    self._logger.warn(
                        'Excluding datastore {ds} on host {host} as it is '
                        'not healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )

            if len(healthy_datastores) == 0:
                self._logger.warn(
                    'Host {host} has no usable datastores.'.format(
                        host=host.name,
                    )
                )
            candidate_datastores = []
            for datastore in healthy_datastores:
                weighting = self.calculate_datastore_weighting(
                    datastore=datastore,
                    vm_memory=vm_memory,
                    template=template,
                )
                if weighting:
                    self._logger.debug(
                        'Datastore {ds} on host {host} has suitability '
                        '{weight}'.format(
                            ds=datastore.name,
                            weight=weighting,
                            host=host.name
                        )
                    )
                    candidate_datastores.append((datastore, weighting))
                else:
                    self._logger.warn(
                        'Datastore {ds} on host {host} does not have enough '
                        'free space.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )
            if candidate_datastores:
                candidate_host = host
                candidate_datastore, candidate_datastore_weighting = max(
                    candidate_datastores,
                    key=lambda datastore: datastore[1]
                )

                if not best_datastore:
                    best_host = candidate_host
                    best_datastore = candidate_datastore
                    best_datastore_weighting = candidate_datastore_weighting
                else:
                    if best_datastore_weighting < 0:
                        # Use the most desirable host unless it can't house
                        # the VM's maximum space usage (assuming the entire
                        # virtual disk is filled up), and unless this
                        # datastore can.
                        if candidate_datastore_weighting >= 0:
                            best_host = candidate_host
                            best_datastore = candidate_datastore
                            best_datastore_weighting = (
                                candidate_datastore_weighting
                            )

                if candidate_host == best_host and \
                        candidate_datastore == best_datastore:
                    self._logger.debug(
                        'Host {host} and datastore {datastore} are current '
                        'best candidate. Best datastore weighting '
                        '{weight}.'.format(
                            host=best_host.name,
                            datastore=best_datastore.name,
                            weight=best_datastore_weighting,
                        )
                    )

        if best_host:
            return best_host, best_datastore
        else:
            message = 'No datastores found with enough space.'
            if allowed_datastores:
                message += ' Only these datastores were allowed: {ds}'
                message = message.format(ds=', '.join(allowed_datastores))
            message += ' Only the suitable candidate hosts were checked: '
            message += '{hosts}'.format(hosts=', '.join(
                [candidate[0].name for candidate in candidate_hosts]
            ))
            raise NonRecoverableError(message)

    def get_host_free_memory(self, host):
        """
            Get the amount of unallocated memory on a host.
        """
        total_memory = host.hardware.memorySize // 1024 // 1024
        used_memory = 0
        for vm in host.vm:
            if not vm.summary.config.template:
                try:
                    used_memory += int(vm.summary.config.memorySizeMB)
                except Exception:
                    self._logger.warning(
                        'Incorrect value for memorySizeMB. It is {0}, but '
                        'integer value is expected'.format(
                            vm.summary.config.memorySizeMB))
        return total_memory - used_memory

    def host_cpu_thread_usage_ratio(self, host, vm_cpus):
        """
            Check the usage ratio of actual CPU threads to assigned threads.
            This should give a higher rating to those hosts with less threads
            assigned compared to their total available CPU threads.

            This is used rather than a simple absolute number of cores
            remaining to avoid allocating to a less sensible host if, for
            example, there are two hypervisors, one with 12 CPU threads and
            one with 6, both of which have 4 more virtual CPUs assigned than
            actual CPU threads. In this case, both would be rated at -4, but
            the actual impact on the one with 12 threads would be lower.
        """
        total_threads = host.hardware.cpuInfo.numCpuThreads

        total_assigned = vm_cpus
        for vm in host.vm:
            try:
                total_assigned += int(vm.summary.config.numCpu)
            except Exception:
                self._logger.warning(
                    "Incorrect value for numCpu. "
                    "It is {0} but integer value is expected".format(
                        vm.summary.config.numCpu))
        return total_threads / total_assigned

    def host_memory_usage_ratio(self, host, new_mem):
        """
        Return the proporiton of resulting memory overcommit if a VM with
        new_mem is added to this host.
        """
        free_memory = self.get_host_free_memory(host)
        free_memory_after = free_memory - new_mem
        weight = free_memory_after / (host.hardware.memorySize // 1024 // 1024)

        return weight

    def datastore_is_usable(self, datastore):
        """
            Return True if this datastore is usable for deployments,
            based on its health.
            Return False otherwise.
        """
        return datastore.overallStatus in (
            vim.ManagedEntity.Status.green,
            vim.ManagedEntity.Status.yellow,
        ) and datastore.summary.accessible

    def calculate_datastore_weighting(self,
                                      datastore,
                                      vm_memory,
                                      template):
        """
            Determine how suitable this datastore is for this deployment.
            Returns None if it is not suitable. Otherwise, returns a weighting
            where higher is better.
        """
        # We assign memory in MB, but free space is in B
        vm_memory_e2 = vm_memory * 1024 * 1024

        free_space = datastore.summary.freeSpace
        minimum_disk = template.summary.storage.committed
        maximum_disk = template.summary.storage.uncommitted

        minimum_used = minimum_disk + vm_memory_e2
        maximum_used = minimum_used + maximum_disk

        if free_space - minimum_used < 0:
            return
        else:
            return free_space - maximum_used

    def recurse_resource_pools(self, resource_pool):
        """
            Recursively get all child resource pools given a resource pool.
            Return a list of all resource pools found.
        """
        resource_pool_names = []
        for pool in resource_pool.resourcePool:
            resource_pool_names.append(pool)
            resource_pool_names.extend(self.recurse_resource_pools(pool))
        return resource_pool_names

    def get_host_networks(self, host):
        """
            Get all networks attached to this host.
            Returns a list of dicts in the form:
            {
                'name': <name of network>,
                'switch_distributed': <whether net is distributed>,
            }
        """
        return [
            {
                'name': net.name,
                'switch_distributed': self._port_group_is_distributed(net),
            } for net in host.network
        ]

    def get_host_resource_pools(self, host):
        """
            Get all resource pools available on this host.
            This will work for hosts inside and outside clusters.
            A list of resource pools will be returned, e.g.
            ['Resources', 'myresourcepool', 'anotherone']
        """
        base_resource_pool = host.parent.resourcePool
        resource_pools = [base_resource_pool]
        child_resource_pools = self.recurse_resource_pools(base_resource_pool)
        resource_pools.extend(child_resource_pools)
        return resource_pools

    def get_host_cluster_membership(self, host):
        """
            Return the name of the cluster this host is part of,
            or None if it is not part of a cluster.
        """
        if isinstance(host.parent, vim.ClusterComputeResource) or \
                isinstance(host.parent.obj, vim.ClusterComputeResource):
            return host.parent.name
        else:
            return

    @staticmethod
    def host_is_usable(host):
        """
            Return True if this host is usable for deployments,
            based on its health.
            Return False otherwise.
        """
        healthy_state = host.overallStatus in [vim.ManagedEntity.Status.green,
                                               vim.ManagedEntity.Status.yellow]
        connected = host.summary.runtime.connectionState == 'connected'
        maintenance = host.summary.runtime.inMaintenanceMode

        if healthy_state and connected and not maintenance:
            # TODO: Check license state (will be yellow for bad license)
            return True
        else:
            return False

    def resize_server(self, server, cpus=None, memory=None):
        self._logger.debug('Entering resize reconfiguration.')
        config = vim.vm.ConfigSpec()
        update_required = False
        if cpus is not None:
            try:
                cpus = int(cpus)
            except (ValueError, TypeError) as e:
                raise NonRecoverableError(
                    "Invalid cpus value: {err}".format(err=e))
            if cpus < 1:
                raise NonRecoverableError(
                    "cpus must be at least 1. Is {cpus}".format(cpus=cpus))
            if server.config.hardware.numCPU != cpus:
                config.numCPUs = cpus
                update_required = True

        if memory:
            try:
                memory = int(memory)
            except (ValueError, TypeError) as e:
                raise NonRecoverableError(
                    'Invalid memory value: {err}'.format(err=e))
            if memory < 512:
                raise NonRecoverableError(
                    'Memory must be at least 512MB. Is {memory}'.format(
                        memory=memory))
            if memory % 128:
                raise NonRecoverableError(
                    'Memory must be an integer multiple of 128. '
                    'Is {memory}'.format(memory=memory))
            if server.config.hardware.memoryMB != memory:
                config.memoryMB = memory
                update_required = True

        if update_required:
            task = server.obj.Reconfigure(spec=config)

            try:
                self._wait_for_task(task)
            except NonRecoverableError as e:
                if 'configSpec.memoryMB' in e.args[0]:
                    raise NonRecoverableError(
                        "Memory error resizing Server. May be caused by "
                        "https://kb.vmware.com/kb/2008405 . If so the Server "
                        "may be resized while it is switched off.",
                        e,
                    )
                raise

        self._logger.debug(
            "Server '%s' resized with new number of "
            "CPUs: %s and RAM: %s." % (server.name, cpus, memory))

    def get_server_ip(self, vm, network_name, ignore_local=True):
        self._logger.debug(
            'Getting server IP from {network}.'.format(
                network=network_name,
            )
        )

        for network in vm.guest.net:
            if not network.network:
                self._logger.warn(
                    'Ignoring device with MAC {mac} as it is not on a '
                    'vSphere network.'.format(
                        mac=network.macAddress,
                    )
                )
                continue
            if network.network and \
                    network_name.lower() == self._get_normalised_name(
                        network.network) and len(network.ipAddress) > 0:
                ip_address = get_ip_from_vsphere_nic_ips(network, ignore_local)
                # This should be debug, but left as info until CFY-4867 makes
                # logs more visible
                self._logger.info(
                    'Found {ip} from device with MAC {mac}'.format(
                        ip=ip_address,
                        mac=network.macAddress,
                    )
                )
                return ip_address

    def _task_guest_state_is_running(self, vm):
        try:
            self._logger.debug("VM state: {state}".format(
                state=vm.guest.guestState))
            return vm.guest.guestState == "running"
        except vmodl.fault.ManagedObjectNotFound:
            raise NonRecoverableError(
                'Server failed to enter running state, task has been deleted '
                'by vCenter after failing.'
            )

    def _task_guest_has_networks(self, vm, adaptermaps):
        # We should possibly be checking that it has the number of networks
        # expected here, but investigation will be required to confirm this
        # behaves as expected (and the VM state check later handles it anyway)
        if len(adaptermaps) == 0:
            return True
        else:
            if len(vm.guest.net) > 0:
                return True
            else:
                return False

    def _wait_vm_running(self, vm, adaptermaps, other=False):
        # check VM state
        if not self._task_guest_state_is_running(vm):
            return False

        # skip guests check for other
        if other:
            self._logger.info("Skip guest checks for other os")
            return True

        # check guest networks
        if not self._task_guest_has_networks(vm, adaptermaps):
            return False

        # everything looks good
        return True
