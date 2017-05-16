# Stdlib imports

# Third party imports
from pyVmomi import vim

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

# This package imports
from cloudify_vsphere.utils.feedback import logger
from vsphere_plugin_common import _with_client, VsphereClient


class NetworkClient(VsphereClient):

    def get_host_list(self, force_refresh=False):
        # Each invocation of this takes up to a few seconds, so try to avoid
        # calling it too frequently by caching
        if hasattr(self, 'host_list') and not force_refresh:
            return self.host_list
        self.host_list = self._get_hosts()
        return self.host_list

    def delete_port_group(self, name):
        logger().debug("Deleting port group {name}.".format(name=name))
        for host in self.get_host_list():
            host.configManager.networkSystem.RemovePortGroup(name)
        logger().debug("Port group {name} was deleted.".format(name=name))

    def get_vswitches(self):
        logger().debug('Getting list of vswitches')

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

        logger().debug('Found vswitches'.format(vswitches=vswitches))
        return vswitches

    def get_dvswitches(self):
        logger().debug('Getting list of dvswitches')

        # This does not currently address multiple datacenters (indeed,
        # much of this code will probably have issues in such an environment).
        dvswitches = self._get_dvswitches()
        dvswitches = [dvswitch.name for dvswitch in dvswitches]

        logger().debug('Found dvswitches'.format(dvswitches=dvswitches))
        return dvswitches

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        logger().debug("Entering create port procedure.")
        runtime_properties = ctx.instance.runtime_properties
        if 'status' not in runtime_properties.keys():
            runtime_properties['status'] = 'preparing'

        vswitches = self.get_vswitches()

        if runtime_properties['status'] == 'preparing':
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

        if runtime_properties['status'] in ('preparing', 'creating'):
            runtime_properties['status'] = 'creating'
            if 'created_on' not in runtime_properties.keys():
                runtime_properties['created_on'] = []

            hosts = [
                host for host in self.get_host_list()
                if host.name not in runtime_properties['created_on']
            ]

            for host in hosts:
                network_system = host.configManager.networkSystem
                specification = vim.host.PortGroup.Specification()
                specification.name = port_group_name
                specification.vlanId = vlan_id
                specification.vswitchName = vswitch_name
                vswitch = network_system.networkConfig.vswitch[0]
                specification.policy = vswitch.spec.policy
                logger().debug(
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
                runtime_properties['created_on'].append(host.name)

            if self.port_group_is_on_all_hosts(port_group_name):
                runtime_properties['status'] = 'created'
            else:
                return ctx.operation.retry(
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

        # This shouldn't use the cache because it is used to test whether a
        # port group has been created
        port_groups = self._get_networks(use_cache=False)

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

        logger().debug(
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
        logger().debug("Getting port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    logger().debug(
                        "Port group(s) info: \n%s." % "".join(
                            "%s: %s" % item
                            for item in
                            vars(port_group).items()))
                    result.append(port_group)
        return result

    def create_dv_port_group(self, port_group_name, vlan_id, vswitch_name):
        logger().debug("Creating dv port group.")

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

        dv_port_group_type = 'earlyBinding'
        dvswitch = self._get_obj_by_name(
            vim.DistributedVirtualSwitch,
            vswitch_name,
        )
        logger().debug(
            "Distributed vSwitch info: \n%s." % "".join(
                "%s: %s" % item
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
        logger().debug(
            'Adding distributed port group {group_name} to dvSwitch '
            '{dvswitch_name}'.format(
                group_name=port_group_name,
                dvswitch_name=vswitch_name,
            )
        )
        task = dvswitch.obj.AddPortgroup(specification)
        self._wait_for_task(task)
        logger().debug("Port created.")

    def delete_dv_port_group(self, name):
        logger().debug("Deleting dv port group {name}.".format(name=name))
        dv_port_group = self._get_obj_by_name(
            vim.dvs.DistributedVirtualPortgroup,
            name,
        )
        task = dv_port_group.obj.Destroy()
        self._wait_for_task(task)
        logger().debug("Port deleted.")


with_network_client = _with_client('network_client', NetworkClient)
