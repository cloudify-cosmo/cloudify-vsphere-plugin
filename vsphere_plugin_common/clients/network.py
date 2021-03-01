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

# Third party imports
import netaddr
from pyVmomi import vim

# Cloudify imports
from cloudify.exceptions import NonRecoverableError, OperationRetry

# This package imports
from . import VsphereClient
from ..constants import (
    NETWORK_STATUS,
    NETWORK_CREATE_ON,
    VSPHERE_RESOURCE_NAME
)
from .._compat import text_type


class NetworkClient(VsphereClient):

    def get_host_list(self, force_refresh=False):
        # Each invocation of this takes up to a few seconds, so try to avoid
        # calling it too frequently by caching
        if hasattr(self, 'host_list') and not force_refresh:
            # make pylint happy
            return getattr(self, 'host_list')
        self.host_list = self._get_hosts()
        return self.host_list

    def delete_port_group(self, name):
        self._logger.debug("Deleting port group {name}.".format(name=name))
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    host.configManager.networkSystem.RemovePortGroup(name)
        self._logger.debug("Port group {name} was deleted.".format(name=name))

    def get_vswitches(self):
        self._logger.debug('Getting list of vswitches')

        # We only want to list vswitches that are on all hosts, as we will try
        # to create port groups on the same vswitch on every host.
        vswitches = set()
        for host in self._get_hosts():
            conf = host.config
            current_host_vswitches = set()
            for vswitch in conf.network.vswitch:
                current_host_vswitches.add(vswitch.name)
            if len(vswitches) == 0:
                vswitches = current_host_vswitches
            else:
                vswitches = vswitches.union(current_host_vswitches)

        self._logger.debug('Found vswitches: {vswitches}'
                           .format(vswitches=vswitches))
        return vswitches

    def get_vswitch_mtu(self, vswitch_name):
        mtu = -1

        for host in self._get_hosts():
            conf = host.config
            for vswitch in conf.network.vswitch:
                if vswitch_name == vswitch.name:
                    if mtu == -1:
                        mtu = vswitch.mtu
                    elif mtu > vswitch.mtu:
                        mtu = vswitch.mtu
        return mtu

    def get_dvswitches(self):
        self._logger.debug('Getting list of dvswitches')

        # This does not currently address multiple datacenters (indeed,
        # much of this code will probably have issues in such an environment).
        dvswitches = self._get_dvswitches()
        dvswitches = [dvswitch.name for dvswitch in dvswitches]

        self._logger.debug('Found dvswitches: {dvswitches}'
                           .format(dvswitches=dvswitches))
        return dvswitches

    def create_port_group(
        self, port_group_name, vlan_id, vswitch_name, instance
    ):
        self._logger.debug("Entering create port procedure.")
        if NETWORK_STATUS not in instance.runtime_properties:
            instance.runtime_properties[NETWORK_STATUS] = 'preparing'
            instance.update()

        vswitches = self.get_vswitches()

        if instance.runtime_properties[NETWORK_STATUS] == 'preparing':
            if vswitch_name not in vswitches:
                if len(vswitches) == 0:
                    raise NonRecoverableError(
                        'No valid vswitches found. '
                        'Every physical host in the datacenter must have the '
                        'same named vswitches available when not using '
                        'distributed vswitches.'
                    )
                else:
                    raise NonRecoverableError(
                        '{vswitch} was not a valid vswitch name. The valid '
                        'vswitches are: {vswitches}'.format(
                            vswitch=vswitch_name,
                            vswitches=', '.join(vswitches),
                        )
                    )

        if instance.runtime_properties[NETWORK_STATUS] in (
            'preparing', 'creating'
        ):
            instance.runtime_properties[NETWORK_STATUS] = 'creating'
            instance.update()
            if NETWORK_CREATE_ON not in instance.runtime_properties:
                instance.runtime_properties[NETWORK_CREATE_ON] = []

            hosts = [
                host for host in self.get_host_list()
                if host.name not in instance.runtime_properties[
                    NETWORK_CREATE_ON]
            ]

            for host in hosts:
                network_system = host.configManager.networkSystem
                specification = vim.host.PortGroup.Specification()
                specification.name = port_group_name
                specification.vlanId = vlan_id
                specification.vswitchName = vswitch_name
                vswitch = network_system.networkConfig.vswitch[0]
                specification.policy = vswitch.spec.policy
                self._logger.debug(
                    'Adding port group {group_name} to vSwitch '
                    '{vswitch_name} on host {host_name}'.format(
                        group_name=port_group_name,
                        vswitch_name=vswitch_name,
                        host_name=host.name,
                    )
                )
                try:
                    network_system.AddPortGroup(specification)
                except vim.fault.AlreadyExists:
                    # We tried to create it on a previous pass, but didn't see
                    # any confirmation (e.g. due to a problem communicating
                    # with the vCenter)
                    # However, we shouldn't have reached this point if it
                    # existed before we tried to create it anywhere, so it
                    # should be safe to proceed.
                    pass
                instance.runtime_properties[NETWORK_CREATE_ON].append(
                    host.name)
                instance.runtime_properties.dirty = True
                instance.update()

            if self.port_group_is_on_all_hosts(port_group_name):
                instance.runtime_properties[NETWORK_STATUS] = 'created'
                instance.update()
            else:
                raise OperationRetry(
                    'Waiting for port group {name} to be created on all '
                    'hosts.'.format(
                        name=port_group_name,
                    )
                )

    def port_group_is_on_all_hosts(self, port_group_name, distributed=False):
        port_groups, hosts = self._get_port_group_host_count(
            port_group_name,
            distributed,
        )
        return hosts == port_groups

    def _get_port_group_host_count(self, port_group_name, distributed=False):
        hosts = self.get_host_list()
        host_count = len(hosts)

        port_groups = self._get_networks()

        if distributed:
            port_groups = [
                pg
                for pg in port_groups
                if self._port_group_is_distributed(pg)
            ]
        else:
            port_groups = [
                pg
                for pg in port_groups
                if not self._port_group_is_distributed(pg)
            ]

        # Observed to create multiple port groups in some circumstances,
        # but with different amounts of attached hosts
        port_groups = [pg for pg in port_groups if pg.name == port_group_name]

        port_group_counts = [len(pg.host) for pg in port_groups]

        port_group_count = sum(port_group_counts)

        self._logger.debug(
            '{type} group {name} found on {port_group_count} out of '
            '{host_count} hosts.'.format(
                type='Distributed port' if distributed else 'Port',
                name=port_group_name,
                port_group_count=port_group_count,
                host_count=host_count,
            )
        )

        return port_group_count, host_count

    def get_port_group_by_name(self, name):
        self._logger.debug("Getting port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    self._logger.debug(
                        "Port group(s) info: \n%s." % "".join(
                            "%s: %s" % item
                            for item in
                            list(vars(port_group).items())))
                    result.append(port_group)
        return result

    def create_dv_port_group(
        self, port_group_name, vlan_id, vswitch_name, instance
    ):
        self._logger.debug("Creating dv port group.")

        dvswitches = self.get_dvswitches()

        if vswitch_name not in dvswitches:
            if len(dvswitches) == 0:
                raise NonRecoverableError(
                    'No valid dvswitches found. '
                    'A distributed virtual switch must exist for distributed '
                    'port groups to be used.'
                )
            else:
                raise NonRecoverableError(
                    '{dvswitch} was not a valid dvswitch name. The valid '
                    'dvswitches are: {dvswitches}'.format(
                        dvswitch=vswitch_name,
                        dvswitches=', '.join(dvswitches),
                    )
                )

        instance.runtime_properties[NETWORK_STATUS] = 'creating'
        instance.update()

        dv_port_group_type = 'earlyBinding'
        dvswitch = self._get_obj_by_name(
            vim.DistributedVirtualSwitch,
            vswitch_name,
        )
        self._logger.debug("Distributed vSwitch info: {dvswitch}"
                           .format(dvswitch=dvswitch))

        vlan_spec = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(
            vlanId=vlan_id)
        port_settings = \
            vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
                vlan=vlan_spec)
        specification = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(
            name=port_group_name,
            defaultPortConfig=port_settings,
            type=dv_port_group_type)
        self._logger.debug(
            'Adding distributed port group {group_name} to dvSwitch '
            '{dvswitch_name}'.format(
                group_name=port_group_name,
                dvswitch_name=vswitch_name,
            )
        )
        task = dvswitch.obj.AddPortgroup(specification)
        self._wait_for_task(task, instance=instance)
        self._logger.debug("Port created.")

    def delete_dv_port_group(self, name, instance):
        self._logger.debug("Deleting dv port group {name}.".format(name=name))
        dv_port_group = self._get_obj_by_name(
            vim.dvs.DistributedVirtualPortgroup,
            name,
        )
        if dv_port_group:
            task = dv_port_group.obj.Destroy()
            self._wait_for_task(task, instance=instance)
            self._logger.debug("Port deleted.")

    def get_network_cidr(self, name, switch_distributed):
        # search in all datacenters
        for dc in self.si.content.rootFolder.childEntity:
            # select all ipppols
            pools = self.si.content.ipPoolManager.QueryIpPools(dc=dc)
            for pool in pools:
                # check network associations pools
                for association in pool.networkAssociation:
                    # check network type
                    network_distributed = isinstance(
                        association.network,
                        vim.dvs.DistributedVirtualPortgroup)
                    if association.networkName == name and \
                            network_distributed == switch_distributed:
                        # convert network information to CIDR
                        subnet_address = pool.ipv4Config.subnetAddress
                        netmask = pool.ipv4Config.netmask
                        if subnet_address and netmask:
                            return text_type(netaddr.IPNetwork(
                                '{network}/{netmask}'
                                .format(network=subnet_address,
                                        netmask=netmask)))
        # We dont have any ipppols related to network
        return "0.0.0.0/0"

    def get_network_mtu(self, name, switch_distributed):
        if switch_distributed:
            # select virtual port group
            dv_port_group = self._get_obj_by_name(
                vim.dvs.DistributedVirtualPortgroup,
                name,
            )
            if not dv_port_group:
                raise NonRecoverableError(
                    "Unable to get DistributedVirtualPortgroup: {name}"
                    .format(name=text_type(name)))
            # get assigned VirtualSwith
            dvSwitch = dv_port_group.config.distributedVirtualSwitch
            return dvSwitch.obj.config.maxMtu
        else:
            mtu = -1
            # search hosts with vswitches
            hosts = self.get_host_list()
            for host in hosts:
                conf = host.config
                # iterate by vswitches
                for vswitch in conf.network.vswitch:
                    # search port group in linked
                    port_name = "key-vim.host.PortGroup-{name}".format(
                        name=name)
                    # check that we have linked network in portgroup(str list)
                    if port_name in vswitch.portgroup:
                        # use mtu from switch
                        if mtu == -1:
                            mtu = vswitch.mtu
                        elif mtu > vswitch.mtu:
                            mtu = vswitch.mtu
            return mtu

    def create_ippool(self, datacenter_name, ippool, networks):
        # create ip pool only on specific datacenter
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=text_type(datacenter_name)))
        pool = vim.vApp.IpPool(name=ippool['name'])
        pool.ipv4Config = vim.vApp.IpPool.IpPoolConfigInfo()
        pool.ipv4Config.subnetAddress = ippool['subnet']
        pool.ipv4Config.netmask = ippool['netmask']
        pool.ipv4Config.gateway = ippool['gateway']
        pool.ipv4Config.range = ippool['range']
        pool.ipv4Config.dhcpServerAvailable = ippool.get('dhcp', False)
        pool.ipv4Config.ipPoolEnabled = ippool.get('enabled', True)
        # add networks to pool
        for network in networks:
            network_name = network.runtime_properties["network_name"]
            self._logger.debug("Attach network {network} to {pool}."
                               .format(network=network_name,
                                       pool=ippool['name']))
            if network.runtime_properties.get("switch_distributed"):
                # search vim.dvs.DistributedVirtualPortgroup
                dv_port_group = self._get_obj_by_name(
                    vim.dvs.DistributedVirtualPortgroup,
                    network_name,
                )
                pool.networkAssociation.insert(0, vim.vApp.IpPool.Association(
                    network=dv_port_group.obj))
            else:
                # search all networks
                networks = [
                    net for net in self._collect_properties(
                        vim.Network, path_set=["name"],
                    ) if not net['obj']._moId.startswith('dvportgroup')]
                # attach all networks with provided name
                for net in networks:
                    if net[VSPHERE_RESOURCE_NAME] == network_name:
                        pool.networkAssociation.insert(
                            0, vim.vApp.IpPool.Association(network=net['obj']))
        return self.si.content.ipPoolManager.CreateIpPool(dc=dc.obj, pool=pool)

    def delete_ippool(self, datacenter_name, ippool_id):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=text_type(datacenter_name)))
        self.si.content.ipPoolManager.DestroyIpPool(dc=dc.obj, id=ippool_id,
                                                    force=True)


class ControllerClient(VsphereClient):

    def detach_controller(self, vm_id, bus_key, instance):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")
        if not bus_key:
            raise NonRecoverableError("Device Key is not defined")

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)

        config_spec = vim.vm.device.VirtualDeviceSpec()
        config_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.remove

        for dev in vm.config.hardware.device:
            if hasattr(dev, "key"):
                if dev.key == bus_key:
                    config_spec.device = dev
                    break
        else:
            self._logger.debug("Controller is not defined {}".format(bus_key))
            return

        spec = vim.vm.ConfigSpec()
        spec.deviceChange = [config_spec]
        task = vm.obj.ReconfigVM_Task(spec=spec)
        self._wait_for_task(task, instance=instance)

    def attach_controller(self, vm_id, dev_spec, controller_type, instance):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")

        known_keys = instance.runtime_properties.get('known_keys')

        if not known_keys:
            vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
            known_keys = []
            for dev in vm.config.hardware.device:
                if isinstance(dev, controller_type):
                    known_keys.append(dev.key)

            instance.runtime_properties['known_keys'] = known_keys
            instance.runtime_properties.dirty = True
            instance.update()

            spec = vim.vm.ConfigSpec()
            spec.deviceChange = [dev_spec]
            task = vm.obj.ReconfigVM_Task(spec=spec)
            # we need to wait, as we use results directly
            self._wait_for_task(task, instance=instance)

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id, use_cache=False)

        controller_properties = {}
        for dev in vm.config.hardware.device:
            if isinstance(dev, controller_type):
                if dev.key not in known_keys:
                    if hasattr(dev, "busNumber"):
                        controller_properties['busNumber'] = dev.busNumber
                    controller_properties['busKey'] = dev.key
                    break
        else:
            raise NonRecoverableError(
                'Have not found key for new added device')

        del instance.runtime_properties['known_keys']
        instance.runtime_properties.dirty = True
        instance.update()

        return controller_properties

    def generate_scsi_card(self, scsi_properties, vm_id):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)

        bus_number = scsi_properties.get("busNumber", 0)
        adapter_type = scsi_properties.get('adapterType')
        scsi_controller_label = scsi_properties['label']
        unitNumber = scsi_properties.get("scsiCtlrUnitNumber", -1)
        sharedBus = scsi_properties.get("sharedBus")

        scsi_spec = vim.vm.device.VirtualDeviceSpec()

        if adapter_type == "lsilogic":
            summary = "LSI Logic"
            controller_type = vim.vm.device.VirtualLsiLogicController
        elif adapter_type == "lsilogic_sas":
            summary = "LSI Logic Sas"
            controller_type = vim.vm.device.VirtualLsiLogicSASController
        else:
            summary = "VMware paravirtual SCSI"
            controller_type = vim.vm.device.ParaVirtualSCSIController

        for dev in vm.config.hardware.device:
            if hasattr(dev, "busNumber"):
                if bus_number < dev.busNumber:
                    bus_number = dev.busNumber

        scsi_spec.device = controller_type()
        scsi_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

        scsi_spec.device.busNumber = bus_number
        scsi_spec.device.deviceInfo = vim.Description()
        scsi_spec.device.deviceInfo.label = scsi_controller_label
        scsi_spec.device.deviceInfo.summary = summary

        if int(unitNumber) >= 0:
            scsi_spec.device.scsiCtlrUnitNumber = int(unitNumber)
        if 'hotAddRemove' in scsi_properties:
            scsi_spec.device.hotAddRemove = scsi_properties['hotAddRemove']

        sharingType = vim.vm.device.VirtualSCSIController.Sharing
        if sharedBus == "virtualSharing":
            # Virtual disks can be shared between virtual machines on the
            # same server
            scsi_spec.device.sharedBus = sharingType.virtualSharing
        elif sharedBus == "physicalSharing":
            # Virtual disks can be shared between virtual machines on
            # any server
            scsi_spec.device.sharedBus = sharingType.physicalSharing
        else:
            # Virtual disks cannot be shared between virtual machines
            scsi_spec.device.sharedBus = sharingType.noSharing
        return scsi_spec, controller_type

    def generate_ethernet_card(self, ethernet_card_properties):

        network_name = ethernet_card_properties[VSPHERE_RESOURCE_NAME]
        switch_distributed = ethernet_card_properties.get('switch_distributed')
        adapter_type = ethernet_card_properties.get('adapter_type', "Vmxnet3")
        start_connected = ethernet_card_properties.get('start_connected', True)
        allow_guest_control = ethernet_card_properties.get(
            'allow_guest_control', True)
        network_connected = ethernet_card_properties.get(
            'network_connected', True)
        wake_on_lan_enabled = ethernet_card_properties.get(
            'wake_on_lan_enabled', True)
        address_type = ethernet_card_properties.get('address_type', 'assigned')
        mac_address = ethernet_card_properties.get('mac_address')

        if not network_connected and start_connected:
            self._logger.debug(
                "Network created unconnected so disable start_connected")
            start_connected = False

        if switch_distributed:
            network_obj = self._get_obj_by_name(
                vim.dvs.DistributedVirtualPortgroup,
                network_name,
            )
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
        self._logger.info('Adding network interface on {name}'.format(
            name=network_name))
        nicspec.operation = \
            vim.vm.device.VirtualDeviceSpec.Operation.add

        if adapter_type == "E1000e":
            controller_type = vim.vm.device.VirtualE1000e
        elif adapter_type == "E1000":
            controller_type = vim.vm.device.VirtualE1000
        elif adapter_type == "Sriov":
            controller_type = vim.vm.device.VirtualSriovEthernetCard
        elif adapter_type == "Vmxnet2":
            controller_type = vim.vm.device.VirtualVmxnet2
        else:
            controller_type = vim.vm.device.VirtualVmxnet3

        nicspec.device = controller_type()
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

        nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nicspec.device.connectable.startConnected = start_connected
        nicspec.device.connectable.allowGuestControl = allow_guest_control
        nicspec.device.connectable.connected = network_connected
        nicspec.device.wakeOnLanEnabled = wake_on_lan_enabled
        nicspec.device.addressType = address_type
        if mac_address:
            nicspec.device.macAddress = mac_address
        return nicspec, controller_type
