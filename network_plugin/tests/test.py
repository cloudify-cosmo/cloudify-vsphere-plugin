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

    def test_network(self):
        self.logger.debug("\nNetwork test started\n")
        name = self.name_prefix + 'net'

        self.logger.debug("Check there is no network \'{0}\'".format(name))
        self.assertThereIsNoNetwork(name)

        ctx = MockCloudifyContext(
            node_id=name,
            node_name=name,
            properties={
                'network': {
                    'vlan_id': network_config['vlan_id'],
                    'vswitch_name': network_config['vswitch_name']
                }
            },
        )
        ctx_patch = mock.patch('network_plugin.network.ctx', ctx)
        ctx_patch.start()
        self.addCleanup(ctx_patch.stop())

        self.logger.debug("Create network \'{0}\'".format(name))
        network_plugin.create()

        self.logger.debug("Check network \'{0}\' is created".format(name))
        net = self.assertThereIsOneAndGetMetaNetwork(name)
        self.logger.debug("Check network \'{0}\' settings".format(name))
        self.assertEqual(name, net['name'])
        self.assertEqual(network_config['vlan_id'], net['vlanId'])

        self.logger.debug("Delete network \'{0}\'".format(name))
        network_plugin.delete()
        self.logger.debug("Check network \'{0}\' is deleted".format(name))
        self.assertThereIsNoNetwork(name)
        self.logger.debug("\nNetwork test finished\n")


if __name__ == '__main__':
    unittest.main()
