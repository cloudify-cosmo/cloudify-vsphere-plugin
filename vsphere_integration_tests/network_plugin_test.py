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

import mock
import unittest
import vsphere_plugin_common as vpc

from cloudify import context
from cloudify import mocks as cfy_mocks
from network_plugin import network
from network_plugin import port
from server_plugin import server as server_plugin
from vsphere_integration_tests import common as tests_common

_tests_config = tests_common.TestsConfig().get()
network_test_config = _tests_config['network_test']
network_config = network_test_config['network']
port_config = network_test_config['port']


class VsphereNetworkTest(tests_common.TestCase):

    def setUp(self):
        super(VsphereNetworkTest, self).setUp()
        self.network_name = self.name_prefix + 'net'

        ctx = cfy_mocks.MockCloudifyContext(
            node_id=self.network_name,
            node_name=self.network_name,
            properties={
                'network': {
                    'vlan_id': network_config['vlan_id'],
                    'vswitch_name': network_config['vswitch_name'],
                    'switch_distributed': network_config['switch_distributed']
                }
            },
        )
        ctx_patch1 = mock.patch('network_plugin.network.cloudify.ctx', ctx)
        ctx_patch1.start()
        ctx_patch2 = mock.patch('vsphere_plugin_common.cloudify.ctx', ctx)
        ctx_patch2.start()
        self.addCleanup(ctx_patch1.stop)
        self.addCleanup(ctx_patch2.stop)
        self.network_client = vpc.NetworkClient().get()

    @unittest.skipIf(network_config['switch_distributed'] is True,
                     "Network 'switch_distributed' property is set to true")
    @unittest.skipIf(tests_common.able_to_connect() is False,
                     "vSphere is not reachable.")
    def test_network(self):
        self.assert_no_port_group(self.network_name)

        network.create()

        net = self.assert_port_group_exist_and_get_info(self.network_name)
        self.assertEqual(self.network_name, net['name'])
        self.assertEqual(network_config['vlan_id'], net['vlanId'])

        network.delete()
        self.assertThereIsNoNetwork(self.network_name)

    @unittest.skipIf(network_config['switch_distributed'] is False,
                     "Network 'switch_distributed' property is set to false")
    @unittest.skipIf(tests_common.able_to_connect() is False,
                     "vSphere is not reachable.")
    def test_network_switch_distributed(self):
        network.create()
        dv_port_group = self.network_client.get_dv_port_group(
            self.network_name)
        self.assertEqual(dv_port_group.config.name, self.network_name)

        network.delete()

        dv_port_group = self.network_client.get_dv_port_group(
            self.network_name)
        self.assertTrue(dv_port_group is None)


class VspherePortTest(tests_common.TestCase):

    def setUp(self):
        super(VspherePortTest, self).setUp()

        port_name = self.name_prefix + 'port'

        vm_name = port_config['vm_name']
        network_name = port_config['network_name']
        switch_distributed = port_config['switch_distributed']

        server_client = vpc.ServerClient().get()
        vm = server_client.get_server_by_name(vm_name)
        vm_runtime_properties = {server_plugin.VSPHERE_SERVER_ID: vm._moId}
        network_runtime_properties = {
            network.NETWORK_NAME: network_name,
            network.SWITCH_DISTRIBUTED: switch_distributed
        }
        vm_instance_context = cfy_mocks.MockNodeInstanceContext(
            runtime_properties=vm_runtime_properties)
        network_instance_context = cfy_mocks.MockNodeInstanceContext(
            runtime_properties=network_runtime_properties)
        vm_relationship = mock.Mock()
        vm_relationship.target = mock.Mock()
        vm_relationship.target.instance = vm_instance_context
        network_relationship = mock.Mock()
        network_relationship.target = mock.Mock()
        network_relationship.target.instance = network_instance_context
        endpoint = None
        instance = cfy_mocks.MockNodeInstanceContext()
        context_capabilities_m = context.ContextCapabilities(
            endpoint, instance)
        get_all_m = mock.Mock()
        get_all_m.values = mock.Mock(
            return_value=[vm_runtime_properties, network_runtime_properties])
        context_capabilities_m.get_all = mock.Mock(return_value=get_all_m)

        ctx = cfy_mocks.MockCloudifyContext(
            node_id=port_name,
            node_name=port_name,
            properties={
                'port': {
                    'mac': port_config['mac'],
                }
            },
            capabilities=context_capabilities_m
        )
        ctx._instance.relationships = [vm_relationship, network_relationship]
        ctx_patch1 = mock.patch('network_plugin.port.cloudify.ctx', ctx)
        ctx_patch1.start()
        ctx_patch2 = mock.patch('vsphere_plugin_common.cloudify.ctx', ctx)
        ctx_patch2.start()
        self.addCleanup(ctx_patch1.stop)
        self.addCleanup(ctx_patch2.stop)
        self.network_client = vpc.NetworkClient().get()

    @unittest.skipIf(port_config['switch_distributed'] is False,
                     "Network 'switch_distributed' property is set to false")
    @unittest.skipIf(tests_common.able_to_connect() is False,
                     "vSphere is not reachable.")
    def test_port_switch_distributed(self):
        port.create()
        port.delete()
