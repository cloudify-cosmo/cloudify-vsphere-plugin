########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import mock
from vsphere_plugin_common import ServerClient
from cosmo_tester.framework.testenv import TestCase
from pyVim.connect import Disconnect
from pyVmomi import vim
from . import categorise_calls
import copy


class VsphereIntegrationTest(TestCase):
    get_vm_expected_calls = {
        'get_Datastore_list': 1,
        'get_DistributedVirtualPortgroup_list': 1,
        'get_Network_list': 1,
        'get_VirtualMachine_list': 1,
        'get_VmwareDistributedVirtualSwitch_list': 1,
        'get_containerview_session': 5,
        'get_properties_content_from_ServiceInstance': 15,
        (
            'get_properties_key,config.distributedVirtualSwitch'
            '_from_DistributedVirtualPortgroup'
        ): 1,
        'get_properties_name,host_from_Network': 1,
        (
            'get_properties_name,overallStatus,summary.accessible,'
            'summary.freeSpace'
            '_from_Datastore'
        ): 1,
        (
            'get_properties_name,summary,config.hardware.device,'
            'datastore,guest.guestState,guest.net,network'
            '_from_VirtualMachine'
        ): 1,
        'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 1,
        'get_service_instance': 1,
        'total': 31,
    }

    get_resource_pools_expected_calls = {
        'get_service_instance': 1,
        'get_properties_content_from_ServiceInstance': 3,
        'get_properties_name,resourcePool_from_ResourcePool': 1,
        'get_ResourcePool_list': 1,
        'get_containerview_session': 1,
        'total': 7,
    }

    get_clusters_expected_calls = {
        'get_ClusterComputeResource_list': 1,
        'get_ResourcePool_list': 1,
        'get_containerview_session': 2,
        'get_properties_content_from_ServiceInstance': 6,
        'get_properties_name,resourcePool_from_ClusterComputeResource': 1,
        'get_properties_name,resourcePool_from_ResourcePool': 1,
        'get_service_instance': 1,
        'total': 13,
    }

    get_computes_expected_calls = {
        'get_ComputeResource_list': 1,
        'get_ResourcePool_list': 1,
        'get_containerview_session': 2,
        'get_properties_content_from_ServiceInstance': 6,
        'get_properties_name,resourcePool_from_ComputeResource': 1,
        'get_properties_name,resourcePool_from_ResourcePool': 1,
        'get_service_instance': 1,
        'total': 13,
    }

    get_datacenters_expected_calls = {
        'get_Datacenter_list': 1,
        'get_containerview_session': 1,
        'get_properties_content_from_ServiceInstance': 3,
        'get_properties_name,vmFolder_from_Datacenter': 1,
        'get_service_instance': 1,
        'total': 7,
    }

    get_datastores_expected_calls = {
        'get_Datastore_list': 1,
        'get_containerview_session': 1,
        'get_properties_content_from_ServiceInstance': 3,
        (
            'get_properties_name,overallStatus,summary.accessible,'
            'summary.freeSpace_from_Datastore'
        ): 1,
        'get_service_instance': 1,
        'total': 7,
    }

    get_networks_expected_calls = {
        'get_DistributedVirtualPortgroup_list': 1,
        'get_Network_list': 1,
        'get_VmwareDistributedVirtualSwitch_list': 1,
        'get_containerview_session': 3,
        'get_properties_content_from_ServiceInstance': 9,
        (
            'get_properties_key,'
            'config.distributedVirtualSwitch_from_DistributedVirtualPortgroup'
        ): 1,
        'get_properties_name,host_from_Network': 1,
        'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 1,
        'get_service_instance': 1,
        'total': 19,
    }

    get_dv_networks_expected_calls = get_networks_expected_calls

    get_dvswitches_expected_calls = {
        'get_VmwareDistributedVirtualSwitch_list': 1,
        'get_containerview_session': 1,
        'get_properties_content_from_ServiceInstance': 3,
        'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 1,
        'get_service_instance': 1,
        'total': 7,
    }

    get_vms_expected_calls = {
        'get_Datastore_list': 1,
        'get_DistributedVirtualPortgroup_list': 1,
        'get_Network_list': 1,
        'get_VirtualMachine_list': 1,
        'get_VmwareDistributedVirtualSwitch_list': 1,
        'get_containerview_session': 5,
        'get_properties_content_from_ServiceInstance': 15,
        (
            'get_properties_key,'
            'config.distributedVirtualSwitch_from_DistributedVirtualPortgroup'
        ): 1,
        'get_properties_name,host_from_Network': 1,
        (
            'get_properties_name,overallStatus,summary.accessible,'
            'summary.freeSpace_from_Datastore'
        ): 1,
        (
            'get_properties_name,summary,config.hardware.device,datastore,'
            'guest.guestState,guest.net,network_from_VirtualMachine'
        ): 1,
        'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 1,
        'get_service_instance': 1,
        'total': 31,
    }

    get_hosts_expected_calls = {
        'get_ClusterComputeResource_list': 1,
        'get_ComputeResource_list': 1,
        'get_Datastore_list': 1,
        'get_DistributedVirtualPortgroup_list': 1,
        'get_HostSystem_list': 1,
        'get_Network_list': 1,
        'get_ResourcePool_list': 1,
        'get_VirtualMachine_list': 1,
        'get_VmwareDistributedVirtualSwitch_list': 1,
        'get_containerview_session': 9,
        'get_properties_content_from_ServiceInstance': 27,
        (
            'get_properties_key,'
            'config.distributedVirtualSwitch'
            '_from_DistributedVirtualPortgroup'
        ): 1,
        'get_properties_name,host_from_Network': 1,
        (
            'get_properties_name,overallStatus,summary.accessible,'
            'summary.freeSpace_from_Datastore'
        ): 1,
        (
            'get_properties_name,parent,hardware.memorySize,'
            'hardware.cpuInfo.numCpuThreads,overallStatus,network,'
            'summary.runtime.connectionState,vm,datastore,'
            'config.network.vswitch,configManager_from_HostSystem'
        ): 1,
        'get_properties_name,resourcePool_from_ClusterComputeResource': 1,
        'get_properties_name,resourcePool_from_ComputeResource': 1,
        'get_properties_name,resourcePool_from_ResourcePool': 1,
        (
            'get_properties_name,summary,config.hardware.device,datastore,'
            'guest.guestState,guest.net,network_from_VirtualMachine'
        ): 1,
        'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 1,
        'get_service_instance': 1,
        'total': 55,
    }

    base_expected_attrs = [
        'name',
        'id',
        'obj',
    ]

    def setUp(self):
        super(VsphereIntegrationTest, self).setUp()
        self.cfg = {
            'host': self.env.cloudify_config['vsphere_host'],
            'username': self.env.cloudify_config['vsphere_username'],
            'password': self.env.cloudify_config['vsphere_password'],
            'port': self.env.cloudify_config.get('vsphere_port', 443),
        }

        self.client = ServerClient()
        self.client.connect(cfg=self.cfg)
        self.platform_caller = mock.patch.object(
            self.client.si._stub, 'InvokeMethod',
            wraps=self.client.si._stub.InvokeMethod,
        ).start()

    def tearDown(self):
        Disconnect(self.client.si)
        self.platform_caller = None

    def _get_nocache_expectation(self, original_calls):
        calls = copy.copy(original_calls)
        for call in calls:
            if call == 'get_service_instance':
                # This is the connection to the platform, so only one is
                # expected to be made per instance of the client
                pass
            elif call == 'total':
                calls[call] *= 2
                # One less get_service_instance
                calls[call] -= 1
            else:
                calls[call] *= 2
        return calls

    # No matter what exists on the platform, we want get_obj methods to make a
    # known amount of calls, to avoid a repeat of VSPHERE-85's DoS.
    # This amount of calls MUST NOT depend on what is on the platform.
    # e.g. we must not make 10 more calls for VMs on a platform with 10 more
    # VMs.
    def test_get_obj_by_id_call_count(self):
        self.client._get_obj_by_id(vim.VirtualMachine,
                                   'thisdoesnotexistonvsphere35u2395')
        expected_calls = self.get_vm_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_obj_by_id_caches(self):
        self.client._get_obj_by_id(vim.VirtualMachine,
                                   'thisdoesnotexistonvsphere35u2395')
        self.client._get_obj_by_id(vim.VirtualMachine,
                                   'thisdoesnotexistonvsphere35u2395')
        expected_calls = self.get_vm_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_obj_by_id_no_cache(self):
        self.client._get_obj_by_id(vim.VirtualMachine,
                                   'thisdoesnotexistonvsphere35u2395',
                                   use_cache=False)
        self.client._get_obj_by_id(vim.VirtualMachine,
                                   'thisdoesnotexistonvsphere35u2395',
                                   use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_vm_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_obj_by_name_call_count(self):
        self.client._get_obj_by_name(vim.VirtualMachine,
                                     'thisdoesnotexistonvsphere35u2395')
        expected_calls = self.get_vm_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_obj_by_name_caches(self):
        self.client._get_obj_by_name(vim.VirtualMachine,
                                     'thisdoesnotexistonvsphere35u2395')
        self.client._get_obj_by_name(vim.VirtualMachine,
                                     'thisdoesnotexistonvsphere35u2395')
        expected_calls = self.get_vm_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_obj_by_name_no_cache(self):
        self.client._get_obj_by_name(vim.VirtualMachine,
                                     'thisdoesnotexistonvsphere35u2395',
                                     use_cache=False)
        self.client._get_obj_by_name(vim.VirtualMachine,
                                     'thisdoesnotexistonvsphere35u2395',
                                     use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_vm_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def _check_resource_pool(self, resource_pool):
        self._check_attrs(resource_pool, ['resourcePool'])

        for rp in resource_pool.resourcePool:
            self._check_resource_pool(rp)

    def _check_cluster(self, cluster):
        self._check_attrs(cluster, ['resourcePool'])

        self._check_resource_pool(cluster.resourcePool)

    def _check_compute(self, compute):
        self._check_attrs(compute, ['resourcePool'])

        self._check_resource_pool(compute.resourcePool)

    def _check_datacenter(self, datacenter):
        self._check_attrs(datacenter, ['vmFolder'])

        assert isinstance(datacenter.vmFolder, vim.Folder)

    def _check_datastore(self, datastore):
        self._check_attrs(
            datastore,
            [
                'summary',
                'overallStatus',
            ],
        )

        self._check_attrs(
            datastore.summary,
            [
                'accessible',
                'freeSpace',
            ],
            include_defaults=False,
        )

    def _check_network(self, network):
        if self.client._port_group_is_distributed(network):
            self._check_dv_network(network)
        else:
            self._check_standard_network(network)

    def _check_standard_network(self, network):
        self._check_attrs(
            network,
            [
                'host'
            ],
        )

        for host in network.host:
            self._check_attrs(
                host,
                ['id'],
                include_defaults=False,
            )

    def _check_dv_network(self, network):
        self._check_attrs(
            network,
            [
                'host',
                'key',
                'config',
            ],
        )

        for host in network.host:
            self._check_attrs(
                host,
                ['id'],
                include_defaults=False,
            )

        self._check_attrs(
            network.config,
            [
                'distributedVirtualSwitch',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            network.config.distributedVirtualSwitch,
            [
                'uuid',
            ],
        )

    def _check_dv_switch(self, dvswitch):
        self._check_attrs(
            dvswitch,
            [
                'uuid',
            ],
        )

    def _check_vm(self, vm):
        self._check_attrs(
            vm,
            [
                'summary',
                'config',
                'datastore',
                'guest',
                'network',
            ],
        )

        self._check_attrs(
            vm.summary,
            [
                'config',
                'runtime',
                'storage',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            vm.summary.config,
            [
                'template',
                'memorySizeMB',
                'numCpu',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            vm.summary.runtime,
            [
                'powerState',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            vm.summary.storage,
            [
                'committed',
                'uncommitted',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            vm.guest,
            [
                'guestState',
                'net',
            ],
            include_defaults=False,
        )

        for datastore in vm.datastore:
            self._check_datastore(datastore)

        for network in vm.network:
            self._check_network(network)

        self._check_attrs(
            vm.config,
            [
                'hardware',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            vm.config.hardware,
            [
                'device',
            ],
            include_defaults=False,
        )

        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                self._check_attrs(
                    dev,
                    [
                        'backing',
                    ],
                    include_defaults=False,
                )
                if hasattr(dev.backing, 'port') and isinstance(
                    dev.backing.port,
                    vim.dvs.PortConnection
                ):
                    self._check_attrs(
                        dev.backing.port,
                        [
                            'portgroupKey',
                        ],
                        include_defaults=False,
                    )
                else:
                    self._check_attrs(
                        dev.backing,
                        [
                            'deviceName',
                        ],
                        include_defaults=False,
                    )
            if isinstance(dev, vim.vm.device.VirtualDisk):
                self._check_attrs(
                    dev,
                    [
                        'backing',
                    ],
                    include_defaults=False,
                )
                self._check_attrs(
                    dev.backing,
                    [
                        'fileName',
                    ],
                    include_defaults=False,
                )

    def _check_host(self, host):
        self._check_attrs(
            host,
            [
                'parent',
                'hardware',
                'overallStatus',
                'network',
                'summary',
                'vm',
                'datastore',
                'config',
                'configManager',
            ],
        )

        if host.parent is not None:
            self._check_cluster(host.parent)

        self._check_attrs(
            host.hardware,
            [
                'memorySize',
                'cpuInfo',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            host.hardware.cpuInfo,
            [
                'numCpuThreads',
            ],
            include_defaults=False,
        )

        for network in host.network:
            self._check_network(network)

        self._check_attrs(
            host.summary,
            [
                'runtime',
            ],
            include_defaults=False,
        )

        self._check_attrs(
            host.summary.runtime,
            [
                'connectionState',
            ],
            include_defaults=False,
        )

        for vm in host.vm:
            self._check_vm(vm)

        for datastore in host.datastore:
            self._check_datastore(datastore)

        for vswitch in host.config.network.vswitch:
            self._check_attrs(
                vswitch,
                [
                    'name',
                ],
                include_defaults=False,
            )

    def _check_attrs(self, item, extra_expected, include_defaults=True):
        if include_defaults:
            expected_attrs = copy.copy(self.base_expected_attrs)
        else:
            expected_attrs = []
        expected_attrs.extend(
            extra_expected
        )

        for attr in expected_attrs:
            assert hasattr(item, attr)

    def test_get_datastores(self):
        datastores = self.client._get_datastores()

        expected_calls = self.get_datastores_expected_calls

        for datastore in datastores:
            self._check_datastore(datastore)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_datastores_caches(self):
        self.client._get_datastores()
        self.client._get_datastores()
        expected_calls = self.get_datastores_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_datastores_no_cache(self):
        self.client._get_datastores(use_cache=False)
        self.client._get_datastores(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_datastores_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_resource_pools(self):
        rps = self.client._get_resource_pools()

        expected_calls = self.get_resource_pools_expected_calls

        for rp in rps:
            self._check_resource_pool(rp)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_resource_pools_caches(self):
        self.client._get_resource_pools()
        self.client._get_resource_pools()
        expected_calls = self.get_resource_pools_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_resource_pools_no_cache(self):
        self.client._get_resource_pools(use_cache=False)
        self.client._get_resource_pools(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_resource_pools_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_clusters(self):
        clusters = self.client._get_clusters()

        expected_calls = self.get_clusters_expected_calls

        for cluster in clusters:
            self._check_cluster(cluster)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_clusters_caches(self):
        self.client._get_clusters()
        self.client._get_clusters()
        expected_calls = self.get_clusters_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_clusters_no_cache(self):
        self.client._get_clusters(use_cache=False)
        self.client._get_clusters(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_clusters_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_computes(self):
        computes = self.client._get_computes()

        expected_calls = self.get_computes_expected_calls

        for compute in computes:
            self._check_compute(compute)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_computes_caches(self):
        self.client._get_computes()
        self.client._get_computes()
        expected_calls = self.get_computes_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_computes_no_cache(self):
        self.client._get_computes(use_cache=False)
        self.client._get_computes(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_computes_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_datacenters(self):
        datacenters = self.client._get_datacenters()

        expected_calls = self.get_datacenters_expected_calls

        for datacenter in datacenters:
            self._check_datacenter(datacenter)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_datacenters_caches(self):
        self.client._get_datacenters()
        self.client._get_datacenters()
        expected_calls = self.get_datacenters_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_datacenters_no_cache(self):
        self.client._get_datacenters(use_cache=False)
        self.client._get_datacenters(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_datacenters_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_networks(self):
        networks = self.client._get_networks()

        expected_calls = self.get_networks_expected_calls

        for network in networks:
            self._check_network(network)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_networks_caches(self):
        self.client._get_networks()
        self.client._get_networks()
        expected_calls = self.get_networks_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_networks_no_cache(self):
        self.client._get_networks(use_cache=False)
        self.client._get_networks(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_networks_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dv_networks(self):
        dv_networks = self.client._get_dv_networks()

        expected_calls = self.get_dv_networks_expected_calls

        for dv_network in dv_networks:
            self._check_dv_network(dv_network)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dv_networks_caches(self):
        self.client._get_dv_networks()
        self.client._get_dv_networks()
        expected_calls = self.get_dv_networks_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dv_networks_no_cache(self):
        self.client._get_dv_networks(use_cache=False)
        self.client._get_dv_networks(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_dv_networks_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dvswitches(self):
        dvswitches = self.client._get_dvswitches()

        expected_calls = self.get_dvswitches_expected_calls

        for dv_switch in dvswitches:
            self._check_dv_switch(dv_switch)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dvswitches_caches(self):
        self.client._get_dvswitches()
        self.client._get_dvswitches()
        expected_calls = self.get_dvswitches_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_dvswitches_no_cache(self):
        self.client._get_dvswitches(use_cache=False)
        self.client._get_dvswitches(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_dvswitches_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_vms(self):
        vms = self.client._get_vms()

        expected_calls = self.get_vms_expected_calls

        for vm in vms:
            self._check_vm(vm)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_vms_caches(self):
        self.client._get_vms()
        self.client._get_vms()
        expected_calls = self.get_vms_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_vms_no_cache(self):
        self.client._get_vms(use_cache=False)
        self.client._get_vms(use_cache=False)
        expected_calls = self._get_nocache_expectation(
            self.get_vms_expected_calls
        )
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_hosts(self):
        hosts = self.client._get_hosts()

        expected_calls = self.get_hosts_expected_calls

        for host in hosts:
            self._check_host(host)

        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_hosts_caches(self):
        self.client._get_hosts()
        self.client._get_hosts()
        expected_calls = self.get_hosts_expected_calls
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)

    def test_get_hosts_no_cache(self):
        self.client._get_hosts(use_cache=False)
        self.client._get_hosts(use_cache=False)
        # Slightly different to the amount of calls for other no_caches
        expected_calls = {
            'get_ClusterComputeResource_list': 2,
            'get_ComputeResource_list': 2,
            'get_Datastore_list': 4,
            'get_DistributedVirtualPortgroup_list': 4,
            'get_HostSystem_list': 2,
            'get_Network_list': 4,
            'get_ResourcePool_list': 4,
            'get_VirtualMachine_list': 2,
            'get_VmwareDistributedVirtualSwitch_list': 4,
            'get_containerview_session': 28,
            'get_properties_content_from_ServiceInstance': 84,
            (
                'get_properties_key,'
                'config.distributedVirtualSwitch'
                '_from_DistributedVirtualPortgroup'
            ): 4,
            'get_properties_name,host_from_Network': 4,
            (
                'get_properties_name,overallStatus,summary.accessible,'
                'summary.freeSpace_from_Datastore'
            ): 4,
            (
                'get_properties_name,parent,hardware.memorySize,'
                'hardware.cpuInfo.numCpuThreads,overallStatus,network,'
                'summary.runtime.connectionState,vm,datastore,'
                'config.network.vswitch,configManager_from_HostSystem'
            ): 2,
            'get_properties_name,resourcePool_from_ClusterComputeResource': 2,
            'get_properties_name,resourcePool_from_ComputeResource': 2,
            'get_properties_name,resourcePool_from_ResourcePool': 4,
            (
                'get_properties_name,summary,config.hardware.device,'
                'datastore,guest.guestState,guest.net,'
                'network_from_VirtualMachine'
            ): 2,
            'get_properties_name,uuid_from_VmwareDistributedVirtualSwitch': 4,
            'get_service_instance': 1,
            'total': 169,
        }
        calls = categorise_calls(self.platform_caller.call_args_list)
        self.assertEqual(expected_calls, calls)
