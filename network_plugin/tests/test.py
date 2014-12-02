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
import network_plugin.network as network_plugin
import vsphere_plugin_common as common

from cloudify.mocks import MockCloudifyContext


_tests_config = common.TestsConfig().get()
network_config = _tests_config['network_test']


class VsphereNetworkTest(common.TestCase):

    def setUp(self):
        super(VsphereNetworkTest, self).setUp()
        self.network_name = self.name_prefix + 'net'

        ctx = MockCloudifyContext(
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
        ctx_patch1 = mock.patch('network_plugin.network.ctx', ctx)
        ctx_patch1.start()
        ctx_patch2 = mock.patch('vsphere_plugin_common.ctx', ctx)
        ctx_patch2.start()
        self.addCleanup(ctx_patch1.stop)
        self.addCleanup(ctx_patch2.stop)
        self.network_client = common.NetworkClient().get()

    @unittest.skipIf(network_config['switch_distributed'] is True,
                     "Network 'switch_distributed' property is set to true")
    def test_network(self):
        self.assert_no_port_group(self.network_name)

        network_plugin.create()

        net = self.assert_port_group_exist_and_get_info(self.network_name)
        self.assertEqual(self.network_name, net['name'])
        self.assertEqual(network_config['vlan_id'], net['vlanId'])

        network_plugin.delete()
        self.assertThereIsNoNetwork(self.network_name)

    @unittest.skipIf(network_config['switch_distributed'] is False,
                     "Network 'switch_distributed' property is set to false")
    def test_network_switch_distributed(self):
        network_plugin.create()
        dv_port_group = self.network_client.get_dv_port_group(
            self.network_name)
        self.assertEqual(dv_port_group.config.name, self.network_name)

        network_plugin.delete()

        dv_port_group = self.network_client.get_dv_port_group(
            self.network_name)
        self.assertTrue(dv_port_group is None)
