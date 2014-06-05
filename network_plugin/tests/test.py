__author__ = 'Oleksandr_Raskosov'


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
            properties={
                'network': {
                    'vlan_id': network_config['vlan_id'],
                    'vswitch_name': network_config['vswitch_name']
                }
            },
        )

        self.logger.debug("Create network \'{0}\'".format(name))
        network_plugin.create(ctx)

        self.logger.debug("Check network \'{0}\' is created".format(name))
        net = self.assertThereIsOneAndGetMetaNetwork(name)
        self.logger.debug("Check network \'{0}\' settings".format(name))
        self.assertEqual(name, net['name'])
        self.assertEqual(network_config['vlan_id'], net['vlanId'])

        self.logger.debug("Delete network \'{0}\'".format(name))
        network_plugin.delete(ctx)
        self.logger.debug("Check network \'{0}\' is deleted".format(name))
        self.assertThereIsNoNetwork(name)
        self.logger.debug("\nNetwork test finished\n")


if __name__ == '__main__':
    unittest.main()
