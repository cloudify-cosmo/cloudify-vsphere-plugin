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

from mock import Mock, patch, call
import unittest

from cloudify.exceptions import NonRecoverableError
import vsphere_plugin_common


class VspherePluginsCommonTests(unittest.TestCase):

    def _make_mock_host(self,
                        name='host',
                        datastores=None,
                        vms=None,
                        memory=4096,
                        cpus=4,
                        networks=None,
                        resource_pool=None,
                        connected=True,
                        status='green'):
        host = Mock()
        host.name = name
        # Yes, datastore = datastores. See pyvmomi. (and vm->vms)
        host.datastore = datastores or []
        host.vm = vms or []
        host.network = networks or []
        host.hardware.memorySize = memory
        host.hardware.cpuInfo.numCpuThreads = cpus
        host.parent.resourcePool = resource_pool
        host.overallStatus = status

        if connected:
            host.summary.runtime.connectionState = 'connected'
        else:
            host.summary.runtime.connectionState = 'disconnected'

        return host

    def _make_mock_network(self,
                           name='network'):
        network = Mock()
        network.name = name

        return network

    def _make_mock_vm(self,
                      name='vm',
                      is_template=False,
                      memory=1024,
                      cpus=1,
                      min_space=1024,
                      extra_space=3072):
        vm = Mock()
        vm.name = name
        vm.summary.config.template = is_template
        vm.summary.config.memorySizeMB = memory
        vm.summary.config.numCpu = cpus
        vm.summary.storage.committed = min_space
        vm.summary.storage.uncommitted = extra_space

        return vm

    def _make_mock_cluster(self, name):
        cluster = Mock()
        cluster.name = name

        return cluster

    def _make_mock_resource_pool(self,
                                 name='resource_pool',
                                 children=None):
        resource_pool = Mock()
        resource_pool.name = name
        resource_pool.resourcePool = []

        if children:
            for child in children:
                resource_pool.resourcePool.append(
                    self._make_mock_resource_pool(
                        **child
                    )
                )

        return resource_pool

    def _make_mock_datastore(self,
                             name='datastore',
                             status='green',
                             accessible=True,
                             free_space=4096):
        datastore = Mock()
        datastore.name = name
        datastore.overallStatus = status
        datastore.summary.accessible = accessible
        datastore.summary.freeSpace = free_space

        return datastore

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_one_host_unusable(self,
                                                    mock_ctx,
                                                    mock_get_hosts,
                                                    mock_get_clusters,
                                                    mock_host_is_usable,
                                                    mock_cluster_membership,
                                                    mock_get_free_memory,
                                                    mock_get_resource_pools,
                                                    mock_get_networks,
                                                    mock_get_cpu_ratio):
        mock_host_is_usable.side_effect = (False, True, True)
        host_names = ('see', 'hear', 'speak')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts
        intended_memory = 1024
        mock_get_free_memory.return_value = intended_memory
        intended_resource_pool = 'rp'
        mock_get_resource_pools.return_value = [
            self._make_mock_resource_pool(name)
            for name in [intended_resource_pool]
        ]
        intended_nets = [
            {'name': 'say', 'switch_distributed': True},
            {'name': 'wave', 'switch_distributed': False},
        ]
        mock_get_networks.return_value = intended_nets
        intended_cpus = 1
        mock_get_cpu_ratio.return_value = 1.0

        client = vsphere_plugin_common.ServerClient()

        expected_result = [hosts[1], hosts[2]]

        result = client.find_candidate_hosts(
            resource_pool=intended_resource_pool,
            vm_cpus=intended_cpus,
            vm_memory=intended_memory,
            vm_networks=intended_nets,
            allowed_hosts=None,
            allowed_clusters=None,
        )

        mock_ctx.logger.warn.assert_called_once_with(
            'Host {host} not usable due to health status.'.format(
                host=host_names[0],
            ),
        )
        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_free_memory.mock_calls,
            [call(host) for host in (hosts[1], hosts[2])],
        )
        self.assertEqual(
            mock_get_resource_pools.mock_calls,
            [call(host) for host in (hosts[1], hosts[2])],
        )
        self.assertEqual(
            mock_get_networks.mock_calls,
            [call(host) for host in (hosts[1], hosts[2])],
        )
        self.assertEqual(
            mock_get_cpu_ratio.mock_calls,
            [call(host, intended_cpus)
             for host in (hosts[1], hosts[2])],
        )

        # No clusters should mean no membership checks
        self.assertEqual(mock_get_clusters.call_count, 0)
        self.assertEqual(mock_cluster_membership.call_count, 0)

        self.assertEqual(result, expected_result)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_allowed_clusters(self,
                                                   mock_ctx,
                                                   mock_get_hosts,
                                                   mock_get_clusters,
                                                   mock_host_is_usable,
                                                   mock_cluster_membership,
                                                   mock_get_free_memory,
                                                   mock_get_resource_pools,
                                                   mock_get_networks,
                                                   mock_get_cpu_ratio):
        mock_host_is_usable.return_value = True
        host_names = ('see', 'hear', 'speak')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts
        intended_memory = 1024
        mock_get_free_memory.return_value = intended_memory
        intended_resource_pool = 'rp'
        mock_get_resource_pools.return_value = [
            self._make_mock_resource_pool(name)
            for name in [intended_resource_pool]
        ]
        intended_nets = [
            {'name': 'say', 'switch_distributed': True},
            {'name': 'wave', 'switch_distributed': False},
        ]
        mock_get_networks.return_value = intended_nets
        intended_cpus = 1
        mock_get_cpu_ratio.return_value = 1.0
        wrong_cluster = 'fake cluster'
        mock_cluster_membership.side_effect = (
            None,
            wrong_cluster,
            'testcluster',
        )

        client = vsphere_plugin_common.ServerClient()

        expected_result = [hosts[2]]

        result = client.find_candidate_hosts(
            resource_pool=intended_resource_pool,
            vm_cpus=intended_cpus,
            vm_memory=intended_memory,
            vm_networks=intended_nets,
            allowed_hosts=None,
            allowed_clusters=['testcluster'],
        )

        self.assertEqual(
            mock_ctx.logger.warn.mock_calls,
            [
                call(
                    'Host {host} is not in a cluster, '
                    'and allowed clusters have been set.'.format(
                        host=host_names[0],
                    )
                ),
                call(
                    'Host {host} is in cluster {cluster}, '
                    'which is not an allowed cluster.'.format(
                        host=host_names[1],
                        cluster=wrong_cluster,
                    )
                ),
            ],
        )
        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_cluster_membership.mock_calls,
            [call(host) for host in hosts],
        )
        mock_get_free_memory.assert_called_once_with(hosts[2])
        mock_get_resource_pools.assert_called_once_with(hosts[2])
        mock_get_networks.assert_called_once_with(hosts[2])
        mock_get_cpu_ratio.assert_called_once_with(hosts[2], intended_cpus)

        mock_get_clusters.assert_called_once_with()

        self.assertEqual(result, expected_result)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_insufficient_memory(self,
                                                      mock_ctx,
                                                      mock_get_hosts,
                                                      mock_get_clusters,
                                                      mock_host_is_usable,
                                                      mock_cluster_membership,
                                                      mock_get_free_memory,
                                                      mock_get_resource_pools,
                                                      mock_get_networks,
                                                      mock_get_cpu_ratio):
        mock_host_is_usable.return_value = True
        host_names = ('see', 'hear', 'speak')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts
        intended_memory = 1024
        mock_get_free_memory.side_effect = (
            intended_memory - 1,
            intended_memory,
            intended_memory,
        )
        intended_resource_pool = 'rp'
        mock_get_resource_pools.return_value = [
            self._make_mock_resource_pool(name)
            for name in [intended_resource_pool]
        ]
        intended_nets = [
            {'name': 'say', 'switch_distributed': True},
            {'name': 'wave', 'switch_distributed': False},
        ]
        mock_get_networks.return_value = intended_nets
        intended_cpus = 1
        mock_get_cpu_ratio.return_value = 1.0

        client = vsphere_plugin_common.ServerClient()

        expected_result = [hosts[1], hosts[2]]

        result = client.find_candidate_hosts(
            resource_pool=intended_resource_pool,
            vm_cpus=intended_cpus,
            vm_memory=intended_memory,
            vm_networks=intended_nets,
            allowed_hosts=None,
            allowed_clusters=None,
        )

        mock_ctx.logger.warn.assert_called_once_with(
            'Host {host} does not have enough free memory.'.format(
                host=host_names[0],
            ),
        )
        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_free_memory.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_resource_pools.mock_calls,
            [call(host) for host in (hosts[1], hosts[2])],
        )
        self.assertEqual(
            mock_get_networks.mock_calls,
            [call(host) for host in (hosts[1], hosts[2])],
        )
        self.assertEqual(
            mock_get_cpu_ratio.mock_calls,
            [call(host, intended_cpus)
             for host in (hosts[1], hosts[2])],
        )

        # No clusters should mean no membership checks
        self.assertEqual(mock_get_clusters.call_count, 0)
        self.assertEqual(mock_cluster_membership.call_count, 0)

        self.assertEqual(result, expected_result)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_bad_networks(self,
                                               mock_ctx,
                                               mock_get_hosts,
                                               mock_get_clusters,
                                               mock_host_is_usable,
                                               mock_cluster_membership,
                                               mock_get_free_memory,
                                               mock_get_resource_pools,
                                               mock_get_networks,
                                               mock_get_cpu_ratio):
        mock_host_is_usable.return_value = True
        host_names = ('see', 'hear', 'speak', 'celebrate')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts
        intended_memory = 1024
        mock_get_free_memory.return_value = intended_memory
        intended_resource_pool = 'rp'
        mock_get_resource_pools.return_value = [
            self._make_mock_resource_pool(name)
            for name in [intended_resource_pool]
        ]
        intended_nets = [
            {'name': 'say', 'switch_distributed': True},
            {'name': 'wave', 'switch_distributed': False},
        ]
        mock_get_networks.side_effect = (
            [intended_nets[0]],
            [intended_nets[1]],
            [],
            intended_nets,
        )
        intended_cpus = 1
        mock_get_cpu_ratio.return_value = 1.0

        client = vsphere_plugin_common.ServerClient()

        expected_result = [hosts[3]]

        result = client.find_candidate_hosts(
            resource_pool=intended_resource_pool,
            vm_cpus=intended_cpus,
            vm_memory=intended_memory,
            vm_networks=intended_nets,
            allowed_hosts=None,
            allowed_clusters=None,
        )

        self.assertEqual(
            mock_ctx.logger.warn.mock_calls,
            [
                call(
                    'Host {host} does not have all required networks. '
                    'Missing standard networks: {net}. '.format(
                        host=host_names[0],
                        net=intended_nets[1]['name'],
                    )
                ),
                call(
                    'Host {host} does not have all required networks. '
                    'Missing distributed networks: {net}. '.format(
                        host=host_names[1],
                        net=intended_nets[0]['name'],
                    )
                ),
                call(
                    'Host {host} does not have all required networks. '
                    'Missing standard networks: {net1}. '
                    'Missing distributed networks: {net2}. '.format(
                        host=host_names[2],
                        net1=intended_nets[1]['name'],
                        net2=intended_nets[0]['name'],
                    )
                ),
            ],
        )

        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_free_memory.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_resource_pools.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_networks.mock_calls,
            [call(host) for host in hosts],
        )
        mock_get_cpu_ratio.assert_called_once_with(hosts[3], intended_cpus)

        # No clusters should mean no membership checks
        self.assertEqual(mock_get_clusters.call_count, 0)
        self.assertEqual(mock_cluster_membership.call_count, 0)

        self.assertEqual(result, expected_result)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_all_unusable(self,
                                               mock_ctx,
                                               mock_get_hosts,
                                               mock_get_clusters,
                                               mock_host_is_usable,
                                               mock_cluster_membership,
                                               mock_get_free_memory,
                                               mock_get_resource_pools,
                                               mock_get_networks,
                                               mock_get_cpu_ratio):
        mock_host_is_usable.return_value = False
        host_names = ('see', 'hear', 'speak')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts

        client = vsphere_plugin_common.ServerClient()

        # Using try/except pattern because some plugins are using testtool,
        # which doesn't support the context aware assertRaises so maintaining
        # consistency in this fashion until standardisation.
        try:
            client.find_candidate_hosts(
                resource_pool='rp',
                vm_cpus=1,
                vm_memory=1024,
                vm_networks=[],
                allowed_hosts=None,
                allowed_clusters=None,
            )
        except NonRecoverableError as err:
            assert 'No healthy hosts' in str(err)

        self.assertEqual(
            mock_ctx.logger.warn.mock_calls,
            [
                call(
                    'Host {host} not usable due to health status.'.format(
                        host=host,
                    )
                )
                for host in host_names
            ],
        )
        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_free_memory.call_count,
            0,
        )
        self.assertEqual(
            mock_get_resource_pools.call_count,
            0,
        )
        self.assertEqual(
            mock_get_networks.call_count,
            0,
        )
        self.assertEqual(
            mock_get_cpu_ratio.call_count,
            0
        )

        # No clusters should mean no membership checks
        self.assertEqual(mock_get_clusters.call_count, 0)
        self.assertEqual(mock_cluster_membership.call_count, 0)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_no_allowed_usable(self,
                                                    mock_ctx,
                                                    mock_get_hosts,
                                                    mock_get_clusters,
                                                    mock_host_is_usable,
                                                    mock_cluster_membership,
                                                    mock_get_free_memory,
                                                    mock_get_resource_pools,
                                                    mock_get_networks,
                                                    mock_get_cpu_ratio):
        mock_host_is_usable.return_value = False
        host_names = ('see', 'hear', 'speak')
        allowed_hosts = [host_names[0]]
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts

        client = vsphere_plugin_common.ServerClient()

        # Using try/except pattern because some plugins are using testtool,
        # which doesn't support the context aware assertRaises so maintaining
        # consistency in this fashion until standardisation.
        try:
            client.find_candidate_hosts(
                resource_pool='rp',
                vm_cpus=1,
                vm_memory=1024,
                vm_networks=[],
                allowed_hosts=allowed_hosts,
                allowed_clusters=None,
            )
        except NonRecoverableError as err:
            assert 'No healthy hosts' in str(err)
            assert "Only these hosts" in str(err)
            assert ', '.join(allowed_hosts) in str(err)

        mock_ctx.logger.warn.assert_called_once_with(
            'Host {host} not usable due to health status.'.format(
                host=host_names[0],
            ),
        )
        mock_host_is_usable.assert_called_once_with(hosts[0])
        self.assertEqual(
            mock_get_free_memory.call_count,
            0,
        )
        self.assertEqual(
            mock_get_resource_pools.call_count,
            0,
        )
        self.assertEqual(
            mock_get_networks.call_count,
            0,
        )
        self.assertEqual(
            mock_get_cpu_ratio.call_count,
            0
        )

        # No clusters should mean no membership checks
        self.assertEqual(mock_get_clusters.call_count, 0)
        self.assertEqual(mock_cluster_membership.call_count, 0)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_no_usable_clusters(self,
                                                     mock_ctx,
                                                     mock_get_hosts,
                                                     mock_get_clusters,
                                                     mock_host_is_usable,
                                                     mock_cluster_membership,
                                                     mock_get_free_memory,
                                                     mock_get_resource_pools,
                                                     mock_get_networks,
                                                     mock_get_cpu_ratio):
        mock_host_is_usable.return_value = False
        host_names = ('see', 'hear', 'speak')
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts

        client = vsphere_plugin_common.ServerClient()

        allowed_clusters = ['hello', 'goodbye']
        mock_cluster_membership.return_value = allowed_clusters[0]

        # Using try/except pattern because some plugins are using testtool,
        # which doesn't support the context aware assertRaises so maintaining
        # consistency in this fashion until standardisation.
        try:
            client.find_candidate_hosts(
                resource_pool='rp',
                vm_cpus=1,
                vm_memory=1024,
                vm_networks=[],
                allowed_hosts=None,
                allowed_clusters=allowed_clusters,
            )
        except NonRecoverableError as err:
            assert 'No healthy hosts' in str(err)
            assert "Only hosts in these clusters" in str(err)
            assert ', '.join(allowed_clusters) in str(err)

        self.assertEqual(
            mock_ctx.logger.warn.mock_calls,
            [
                call(
                    'Host {host} not usable due to health status.'.format(
                        host=host,
                    )
                )
                for host in host_names
            ],
        )
        self.assertEqual(
            mock_host_is_usable.mock_calls,
            [call(host) for host in hosts],
        )
        self.assertEqual(
            mock_get_free_memory.call_count,
            0,
        )
        self.assertEqual(
            mock_get_resource_pools.call_count,
            0,
        )
        self.assertEqual(
            mock_get_networks.call_count,
            0,
        )
        self.assertEqual(
            mock_get_cpu_ratio.call_count,
            0
        )
        mock_get_clusters.assert_called_once_with()

        # Unhealthy hosts should not be subject to membership checks
        self.assertEqual(mock_cluster_membership.call_count, 0)

    @patch('vsphere_plugin_common.ServerClient.host_cpu_thread_usage_ratio')
    @patch('vsphere_plugin_common.ServerClient.get_host_networks')
    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    @patch('vsphere_plugin_common.ServerClient.get_host_free_memory')
    @patch('vsphere_plugin_common.ServerClient.get_host_cluster_membership')
    @patch('vsphere_plugin_common.ServerClient.host_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_clusters')
    @patch('vsphere_plugin_common.VsphereClient._get_hosts')
    @patch('vsphere_plugin_common.ctx')
    def test_find_candidate_hosts_bad_cluster_hosts(self,
                                                    mock_ctx,
                                                    mock_get_hosts,
                                                    mock_get_clusters,
                                                    mock_host_is_usable,
                                                    mock_cluster_membership,
                                                    mock_get_free_memory,
                                                    mock_get_resource_pools,
                                                    mock_get_networks,
                                                    mock_get_cpu_ratio):
        mock_host_is_usable.return_value = False
        host_names = ('see', 'hear', 'speak')
        allowed_hosts = [host_names[2]]
        hosts = [
            self._make_mock_host(name)
            for name in host_names
        ]
        mock_get_hosts.return_value = hosts

        client = vsphere_plugin_common.ServerClient()

        allowed_clusters = ['hello', 'goodbye']
        mock_cluster_membership.return_value = 'see_cluster'

        # Using try/except pattern because some plugins are using testtool,
        # which doesn't support the context aware assertRaises so maintaining
        # consistency in this fashion until standardisation.
        try:
            client.find_candidate_hosts(
                resource_pool='rp',
                vm_cpus=1,
                vm_memory=1024,
                vm_networks=[],
                allowed_hosts=allowed_hosts,
                allowed_clusters=allowed_clusters,
            )
        except NonRecoverableError as err:
            assert 'No healthy hosts' in str(err)
            assert "Only hosts in these clusters" in str(err)
            assert ', '.join(allowed_clusters) in str(err)
            assert "Only these hosts" in str(err)
            assert ', '.join(allowed_hosts) in str(err)

        mock_ctx.logger.warn.assert_called_once_with(
            'Host {host} not usable due to health status.'.format(
                host=allowed_hosts[0],
            )
        )
        mock_host_is_usable.assert_called_once_with(hosts[2])
        self.assertEqual(
            mock_get_free_memory.call_count,
            0,
        )
        self.assertEqual(
            mock_get_resource_pools.call_count,
            0,
        )
        self.assertEqual(
            mock_get_networks.call_count,
            0,
        )
        self.assertEqual(
            mock_get_cpu_ratio.call_count,
            0
        )
        mock_get_clusters.assert_called_once_with()

        # Unhealthy hosts should not be subject to membership checks
        self.assertEqual(mock_cluster_membership.call_count, 0)

    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    def test_get_resource_pool_exists(self, mock_get_host_resource_pools):
        pool_name = 'mypool'
        host_pools = [
            self._make_mock_resource_pool(name)
            for name in (pool_name, 'this', 'that')
        ]
        mock_get_host_resource_pools.return_value = host_pools

        host = self._make_mock_host('myhost')

        expected = host_pools[0]

        client = vsphere_plugin_common.ServerClient()

        result = client.get_resource_pool(host, pool_name)

        self.assertEqual(result, expected)

        mock_get_host_resource_pools.assert_called_once_with(host)

    @patch('vsphere_plugin_common.ServerClient.get_host_resource_pools')
    def test_get_resource_pool_fail(self, mock_get_host_resource_pools):
        pool_name = 'mypool'
        pools = ('this', 'that')
        host_pools = [
            self._make_mock_resource_pool(name)
            for name in pools
        ]
        mock_get_host_resource_pools.return_value = host_pools

        host = self._make_mock_host('myhost')

        client = vsphere_plugin_common.ServerClient()

        try:
            client.get_resource_pool(host, pool_name)
        except NonRecoverableError as err:
            missing = 'Resource pool {pool} not found on host {host}'.format(
                pool=pool_name,
                host=host.name,
            )
            assert missing in str(err)
            assert ', '.join(pools) in str(err)

        mock_get_host_resource_pools.assert_called_once_with(host)

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_none_allowed(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        hosts = [
            self._make_mock_host(
                name='host1',
                datastores=[
                    self._make_mock_datastore(
                        name='mydatastore',
                    )
                ],
            ),
        ]
        template = self._make_mock_vm(name='mytemplate')
        allowed_datastores = ['none at all', 'except this one']

        client = vsphere_plugin_common.ServerClient()

        try:
            client.select_host_and_datastore(
                candidate_hosts=hosts,
                vm_memory=1024,
                template=template,
                allowed_datastores=allowed_datastores,
            )
        except NonRecoverableError as err:
            assert 'No datastores found' in str(err)
            assert 'Only these datastores were allowed' in str(err)
            assert ', '.join(allowed_datastores) in str(err)
            assert ', '.join(host.name for host in hosts)

        mock_ctx.logger.warn.assert_called_once_with(
            'Host {host} had no allowed datastores.'.format(
                host=hosts[0].name,
            )
        )
        self.assertEqual(mock_datastore_is_usable.call_count, 0)
        self.assertEqual(mock_datastore_weighting.call_count, 0)
        mock_get_datastores.assert_called_once_with()

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_none_usable(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        hosts = [
            self._make_mock_host(
                name='host1',
                datastores=[
                    self._make_mock_datastore(
                        name='mydatastore',
                    )
                ],
            ),
        ]
        mock_datastore_is_usable.return_value = False
        template = self._make_mock_vm(name='mytemplate')

        client = vsphere_plugin_common.ServerClient()

        try:
            client.select_host_and_datastore(
                candidate_hosts=hosts,
                vm_memory=1024,
                template=template,
                allowed_datastores=None,
            )
        except NonRecoverableError as err:
            assert 'No datastores found' in str(err)
            assert ', '.join(host.name for host in hosts)
            assert 'Only these datastores were allowed' not in str(err)

        self.assertEqual(
            mock_ctx.logger.warn.mock_calls,
            [
                call(
                    'Excluding datastore {ds} on host {host} as it is not '
                    'healthy.'.format(
                        ds=hosts[0].datastore[0].name,
                        host=hosts[0].name,
                    ),
                ),
                call(
                    'Host {host} has no usable datastores.'.format(
                        host=hosts[0].name,
                    ),
                ),
            ],
        )
        mock_datastore_is_usable.assert_called_once_with(
            hosts[0].datastore[0],
        )
        self.assertEqual(mock_datastore_weighting.call_count, 0)

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_insufficient_space(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        hosts = [
            self._make_mock_host(
                name='host1',
                datastores=[
                    self._make_mock_datastore(
                        name='mydatastore',
                    )
                ],
            ),
        ]
        mock_datastore_is_usable.return_value = True
        template = self._make_mock_vm(name='mytemplate')
        mock_datastore_weighting.return_value = None

        memory = 1024
        client = vsphere_plugin_common.ServerClient()

        try:
            client.select_host_and_datastore(
                candidate_hosts=hosts,
                vm_memory=memory,
                template=template,
                allowed_datastores=None,
            )
        except NonRecoverableError as err:
            assert 'No datastores found' in str(err)
            assert ', '.join(host.name for host in hosts)
            assert 'Only these datastores were allowed' not in str(err)

        mock_ctx.logger.warn.assert_called_once_with(
            'Datastore {ds} on host {host} does not have enough free '
            'space.'.format(
                ds=hosts[0].datastore[0].name,
                host=hosts[0].name,
            ),
        )
        mock_datastore_is_usable.assert_called_once_with(
            hosts[0].datastore[0],
        )
        mock_datastore_weighting.assert_called_once_with(
            datastore=hosts[0].datastore[0],
            vm_memory=memory,
            template=template,
        )

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_use_allowed(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        right_datastore = self._make_mock_datastore(
            name='mydatastore',
        )
        wrong_datastore = self._make_mock_datastore(
            name='notthisone',
        )
        right_host = self._make_mock_host(
            name='host2',
            datastores=[
                right_datastore,
                wrong_datastore,
            ],
        )
        hosts = [
            self._make_mock_host(
                name='host1',
                datastores=[wrong_datastore],
            ),
            right_host,
            self._make_mock_host(
                name='host3',
                datastores=[wrong_datastore],
            ),
        ]
        mock_datastore_is_usable.return_value = True
        template = self._make_mock_vm(name='mytemplate')
        mock_datastore_weighting.return_value = 1

        memory = 1024
        allowed_datastores = [right_datastore.name]

        client = vsphere_plugin_common.ServerClient()

        expected = right_host, right_datastore

        result = client.select_host_and_datastore(
            candidate_hosts=hosts,
            vm_memory=memory,
            template=template,
            allowed_datastores=allowed_datastores,
        )

        self.assertEqual(result, expected)

        mock_datastore_is_usable.assert_called_once_with(right_datastore)
        mock_datastore_weighting.assert_called_once_with(
            datastore=right_datastore,
            vm_memory=memory,
            template=template,
        )

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_use_best_ds_on_best_host_if_possible(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        right_datastore = self._make_mock_datastore(
            name='mydatastore',
        )
        wrong_datastore = self._make_mock_datastore(
            name='notthisone',
        )
        right_host = self._make_mock_host(
            name='host2',
            datastores=[
                wrong_datastore,
                right_datastore,
            ],
        )
        hosts = [
            right_host,
            self._make_mock_host(
                name='host1',
                datastores=[wrong_datastore],
            ),
        ]
        mock_datastore_is_usable.return_value = True
        template = self._make_mock_vm(name='mytemplate')
        mock_datastore_weighting.side_effect = (1, 100, 1000)

        memory = 1024

        client = vsphere_plugin_common.ServerClient()

        expected = right_host, right_datastore

        result = client.select_host_and_datastore(
            candidate_hosts=hosts,
            vm_memory=memory,
            template=template,
            allowed_datastores=None,
        )

        self.assertEqual(result, expected)

        self.assertEqual(
            mock_datastore_is_usable.mock_calls,
            [
                call(wrong_datastore),
                call(right_datastore),
                call(wrong_datastore),
            ],
        )
        self.assertEqual(
            mock_datastore_weighting.mock_calls,
            [
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=right_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
            ],
        )

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_use_best_host_if_all_poor_datastores(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        right_datastore = self._make_mock_datastore(
            name='mydatastore',
        )
        wrong_datastore = self._make_mock_datastore(
            name='notthisone',
        )
        right_host = self._make_mock_host(
            name='host2',
            datastores=[
                wrong_datastore,
                right_datastore,
            ],
        )
        hosts = [
            right_host,
            self._make_mock_host(
                name='host1',
                datastores=[wrong_datastore],
            ),
        ]
        mock_datastore_is_usable.return_value = True
        template = self._make_mock_vm(name='mytemplate')
        mock_datastore_weighting.side_effect = (-100, -2, -1)

        memory = 1024

        client = vsphere_plugin_common.ServerClient()

        expected = right_host, right_datastore

        result = client.select_host_and_datastore(
            candidate_hosts=hosts,
            vm_memory=memory,
            template=template,
            allowed_datastores=None,
        )

        self.assertEqual(result, expected)

        self.assertEqual(
            mock_datastore_is_usable.mock_calls,
            [
                call(wrong_datastore),
                call(right_datastore),
                call(wrong_datastore),
            ],
        )
        self.assertEqual(
            mock_datastore_weighting.mock_calls,
            [
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=right_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
            ],
        )

    @patch('vsphere_plugin_common.ServerClient.calculate_datastore_weighting')
    @patch('vsphere_plugin_common.ServerClient.datastore_is_usable')
    @patch('vsphere_plugin_common.ServerClient._get_datastores')
    @patch('vsphere_plugin_common.ctx')
    def test_select_host_and_datastore_use_best_datastore_if_current_poor(
        self,
        mock_ctx,
        mock_get_datastores,
        mock_datastore_is_usable,
        mock_datastore_weighting,
    ):
        right_datastore = self._make_mock_datastore(
            name='mydatastore',
        )
        wrong_datastore = self._make_mock_datastore(
            name='notthisone',
        )
        right_host = self._make_mock_host(
            name='host2',
            datastores=[
                wrong_datastore,
                right_datastore,
            ],
        )
        hosts = [
            self._make_mock_host(
                name='host1',
                datastores=[wrong_datastore],
            ),
            right_host,
        ]
        mock_datastore_is_usable.return_value = True
        template = self._make_mock_vm(name='mytemplate')
        mock_datastore_weighting.side_effect = (-100, -2, 1)

        memory = 1024

        client = vsphere_plugin_common.ServerClient()

        expected = right_host, right_datastore

        result = client.select_host_and_datastore(
            candidate_hosts=hosts,
            vm_memory=memory,
            template=template,
            allowed_datastores=None,
        )

        self.assertEqual(result, expected)

        self.assertEqual(
            mock_datastore_is_usable.mock_calls,
            [
                call(wrong_datastore),
                call(wrong_datastore),
                call(right_datastore),
            ],
        )
        self.assertEqual(
            mock_datastore_weighting.mock_calls,
            [
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=wrong_datastore,
                    vm_memory=memory,
                    template=template,
                ),
                call(
                    datastore=right_datastore,
                    vm_memory=memory,
                    template=template,
                ),
            ],
        )

    def test_get_host_free_memory_no_vms(self):
        expected = 12345
        host = self._make_mock_host(memory=expected)

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_free_memory(host)

        self.assertEqual(result, expected)

    def test_get_host_free_memory_with_vms(self):
        vm1_mem = 10
        vm2_mem = 894
        host_mem = 12345
        expected = host_mem - vm1_mem - vm2_mem

        vms = [
            self._make_mock_vm(memory=vm1_mem),
            self._make_mock_vm(memory=vm2_mem),
        ]
        host = self._make_mock_host(
            memory=host_mem,
            vms=vms,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_free_memory(host)

        self.assertEqual(result, expected)

    def test_host_cpu_thread_usage_ratio_no_vms(self):
        host_cpus = 4
        new_vm_cpus = 4
        expected = float(host_cpus) / new_vm_cpus

        host = self._make_mock_host(
            cpus=host_cpus,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.host_cpu_thread_usage_ratio(
            host=host,
            vm_cpus=new_vm_cpus,
        )

        self.assertEqual(result, expected)

    def test_host_cpu_thread_usage_ratio_with_vms(self):
        host_cpus = 4
        new_vm_cpus = 4
        vm1_cpus = 2
        vm2_cpus = 4

        existing_vms = [
            self._make_mock_vm(cpus=vm1_cpus),
            self._make_mock_vm(cpus=vm2_cpus),
        ]

        total_cpus = vm1_cpus + vm2_cpus + new_vm_cpus

        expected = float(host_cpus) / total_cpus

        host = self._make_mock_host(
            cpus=host_cpus,
            vms=existing_vms,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.host_cpu_thread_usage_ratio(
            host=host,
            vm_cpus=new_vm_cpus,
        )

        self.assertEqual(result, expected)

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_datastore_is_usable_good(self, mock_status):
        mock_status.green = 'green'

        datastore = self._make_mock_datastore(
            status=mock_status.green,
            accessible=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertTrue(client.datastore_is_usable(datastore))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_datastore_is_usable_mostly_good(self, mock_status):
        mock_status.yellow = 'yellow'

        datastore = self._make_mock_datastore(
            status=mock_status.yellow,
            accessible=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertTrue(client.datastore_is_usable(datastore))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_datastore_is_usable_good_but_disconnected(self, mock_status):
        datastore = self._make_mock_datastore(
            accessible=False,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertFalse(client.datastore_is_usable(datastore))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_datastore_is_usable_not_good(self, mock_status):
        datastore = self._make_mock_datastore(
            status='something different',
            accessible=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertFalse(client.datastore_is_usable(datastore))

    def test_calculate_datastore_weighting_insufficient_space(self):
        datastore = self._make_mock_datastore(
            free_space=0,
        )

        template = self._make_mock_vm(
            is_template=True,
            min_space=10,
            extra_space=10,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.calculate_datastore_weighting(
            datastore=datastore,
            template=template,
            vm_memory=10,
        )

        self.assertIsNone(result)

    def test_calculate_datastore_weighting_minimum(self):
        # Bare minimum should be memory (in bytes, we specify in MB)
        # + minimum space used by template
        initial_free = 10485770
        datastore = self._make_mock_datastore(
            free_space=initial_free,
        )
        vm_memory = 10
        min_space = 10
        extra_space = 1000000

        expected_weighting = initial_free - (vm_memory * 1024 * 1024)
        expected_weighting = expected_weighting - min_space - extra_space

        template = self._make_mock_vm(
            is_template=True,
            min_space=min_space,
            extra_space=extra_space,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.calculate_datastore_weighting(
            datastore=datastore,
            template=template,
            vm_memory=vm_memory,
        )

        self.assertEqual(result, expected_weighting)

    def test_calculate_datastore_weighting_more_than_enough(self):
        initial_free = 17179869184
        datastore = self._make_mock_datastore(
            free_space=initial_free,
        )
        vm_memory = 10
        min_space = 10
        extra_space = 10

        expected_weighting = initial_free - (vm_memory * 1024 * 1024)
        expected_weighting = expected_weighting - min_space - extra_space

        template = self._make_mock_vm(
            is_template=True,
            min_space=min_space,
            extra_space=extra_space,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.calculate_datastore_weighting(
            datastore=datastore,
            template=template,
            vm_memory=vm_memory,
        )

        self.assertEqual(result, expected_weighting)

    def test_recurse_resource_pools_no_children(self):
        pool_name = 'pool1'
        expected = []
        pool = self._make_mock_resource_pool(
            name=pool_name,
        )

        client = vsphere_plugin_common.ServerClient()

        result = client.recurse_resource_pools(pool)

        self.assertEqual(result, expected)

    def test_recurse_resource_pools_with_children(self):
        pool1_name = 'pool1'
        pool2_name = 'something'
        pool3_name = 'yes'
        pool4_name = 'scell'
        pool5_name = 'shwg'

        pool = self._make_mock_resource_pool(
            name=pool1_name,
            children=[
                {
                    'name': pool2_name,
                },
                {
                    'name': pool3_name,
                    'children': [
                        {
                            'name': pool4_name,
                        },
                        {
                            'name': pool5_name,
                        },
                    ],
                },
            ],
        )

        expected = [
            pool.resourcePool[0],
            pool.resourcePool[1],
            pool.resourcePool[1].resourcePool[0],
            pool.resourcePool[1].resourcePool[1],
        ]

        client = vsphere_plugin_common.ServerClient()

        result = client.recurse_resource_pools(pool)

        # We should have the same in each list, but order is unimportant
        expected.sort()
        result.sort()

        self.assertEqual(result, expected)

    @patch('vsphere_plugin_common.ServerClient._port_group_is_distributed')
    def test_get_host_networks(self, mock_is_distributed):
        net_names = ('say', 'hello', 'wave', 'goodybe')
        net_distributed = (True, False, True, True)
        mock_is_distributed.side_effect = net_distributed

        expected = [
            {
                'name': net[0],
                'switch_distributed': net[1],
            }
            for net in zip(net_names, net_distributed)
        ]

        nets = [
            self._make_mock_network(name=net)
            for net in net_names
        ]

        host = self._make_mock_host(networks=nets)

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_networks(host)

        self.assertEqual(result, expected)

    @patch('vsphere_plugin_common.ServerClient.recurse_resource_pools')
    def test_get_host_resource_pools_no_children(self, mock_recurse):
        mock_recurse.return_value = []

        base_pool = self._make_mock_resource_pool(name='Resources')

        expected = [base_pool]

        host = self._make_mock_host(resource_pool=base_pool)

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_resource_pools(host)

        self.assertEqual(result, expected)

    @patch('vsphere_plugin_common.ServerClient.recurse_resource_pools')
    def test_get_host_resource_pools_with_children(self, mock_recurse):
        other_pools = [
            self._make_mock_resource_pool(),
            self._make_mock_resource_pool(),
            self._make_mock_resource_pool(),
        ]
        mock_recurse.return_value = other_pools
        base_pool = self._make_mock_resource_pool(name='Resources')

        expected = [base_pool]
        expected.extend(other_pools)

        host = self._make_mock_host(resource_pool=base_pool)

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_resource_pools(host)

        self.assertEqual(result, expected)

    @patch('vsphere_plugin_common.vim.ClusterComputeResource')
    @patch('vsphere_plugin_common.isinstance', create=True)
    def test_get_host_cluster_membership_member(self,
                                                mock_isinstance,
                                                mock_cluster_type):
        expected_name = 'mycluster'
        host = self._make_mock_host()
        host.parent.name = expected_name

        mock_isinstance.return_value = True

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_cluster_membership(host)

        mock_isinstance.assert_called_once_with(
            host.parent,
            mock_cluster_type,
        )

        self.assertEqual(expected_name, result)

    @patch('vsphere_plugin_common.vim.ClusterComputeResource')
    @patch('vsphere_plugin_common.isinstance', create=True)
    def test_get_host_cluster_membership_non_member(self,
                                                    mock_isinstance,
                                                    mock_cluster_type):
        host = self._make_mock_host()

        mock_isinstance.return_value = False

        client = vsphere_plugin_common.ServerClient()

        result = client.get_host_cluster_membership(host)

        mock_isinstance.assert_called_once_with(
            host.parent,
            mock_cluster_type,
        )

        self.assertIsNone(result)

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_host_is_usable_good(self, mock_status):
        mock_status.green = 'green'

        host = self._make_mock_host(
            status=mock_status.green,
            connected=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertTrue(client.host_is_usable(host))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_host_is_usable_mostly_good(self, mock_status):
        mock_status.yellow = 'yellow'

        host = self._make_mock_host(
            status=mock_status.yellow,
            connected=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertTrue(client.host_is_usable(host))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_host_is_usable_good_but_disconnected(self, mock_status):
        mock_status.green = 'green'

        host = self._make_mock_host(
            status=mock_status.green,
            connected=False,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertFalse(client.host_is_usable(host))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_host_is_usable_mostly_good_but_disconnected(self, mock_status):
        mock_status.yellow = 'yellow'

        host = self._make_mock_host(
            status=mock_status.yellow,
            connected=False,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertFalse(client.host_is_usable(host))

    @patch('vsphere_plugin_common.vim.ManagedEntity.Status')
    def test_host_is_usable_not_good(self, mock_status):
        mock_status.other = 'something'

        host = self._make_mock_host(
            status=mock_status.other,
            connected=True,
        )

        client = vsphere_plugin_common.ServerClient()

        self.assertFalse(client.host_is_usable(host))

    @patch('vsphere_plugin_common.vim.dvs.DistributedVirtualPortgroup')
    def test_port_group_is_distributed(self,
                                       mock_distributed_port_group_type):
        port_group = Mock()
        port_group.id = 'dvportgroup-123'

        client = vsphere_plugin_common.ServerClient()

        result = client._port_group_is_distributed(port_group)

        self.assertTrue(result)

    @patch('vsphere_plugin_common.vim.dvs.DistributedVirtualPortgroup')
    def test_port_group_is_not_distributed(self,
                                           mock_distributed_port_group_type):
        port_group = Mock()
        port_group.id = 'somethingelse-456'

        client = vsphere_plugin_common.ServerClient()

        result = client._port_group_is_distributed(port_group)

        self.assertFalse(result)

    @patch('vsphere_plugin_common.ctx')
    def test_resize_server_fails_128(self, ctx):
        client = vsphere_plugin_common.ServerClient()

        with self.assertRaises(NonRecoverableError) as e:
            client.resize_server(None, memory=572)

        self.assertIn('must be an integer multiple of 128', str(e.exception))

    @patch('vsphere_plugin_common.ctx')
    def test_resize_server_fails_512(self, ctx):
        client = vsphere_plugin_common.ServerClient()

        with self.assertRaises(NonRecoverableError) as e:
            client.resize_server(None, memory=128)

        self.assertIn('at least 512MB', str(e.exception))

    @patch('vsphere_plugin_common.ctx')
    def test_resize_server_fails_memory_NaN(self, ctx):
        client = vsphere_plugin_common.ServerClient()

        with self.assertRaises(NonRecoverableError) as e:
            client.resize_server(None, memory='banana')

        self.assertIn('Invalid memory value', str(e.exception))

    @patch('vsphere_plugin_common.ctx')
    def test_resize_server_fails_0_cpus(self, ctx):
        client = vsphere_plugin_common.ServerClient()

        with self.assertRaises(NonRecoverableError) as e:
            client.resize_server(None, cpus=0)

        self.assertIn('must be at least 1', str(e.exception))

    @patch('vsphere_plugin_common.ctx')
    def test_resize_server_fails_cpu_NaN(self, ctx):
        client = vsphere_plugin_common.ServerClient()

        with self.assertRaises(NonRecoverableError) as e:
            client.resize_server(None, cpus='apple')

        self.assertIn('Invalid cpus value', str(e.exception))

    @patch('pyVmomi.vim.vm.ConfigSpec')
    @patch('vsphere_plugin_common.ctx')
    def test_resize_server(self, ctx, configSpec):
        client = vsphere_plugin_common.ServerClient()
        server = Mock()
        server.obj.Reconfigure.return_value.info.state = 'success'

        client.resize_server(server, cpus=3, memory=1024)

        server.obj.Reconfigure.assert_called_once_with(
            spec=configSpec.return_value,
        )
