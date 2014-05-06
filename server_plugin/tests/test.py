__author__ = 'Oleksandr_Raskosov'


import unittest
import server_plugin.server as server_plugin
import vsphere_plugin_common as common
import time

from cloudify.context import ContextCapabilities
from cloudify.mocks import MockCloudifyContext


WAIT_START = 10
WAIT_FACTOR = 2
WAIT_COUNT = 6


_tests_config = common.TestsConfig().get()
server_config = _tests_config['server_test']


class VsphereServerTest(common.TestCase):

    def test_server(self):
        self.logger.debug("\nServer test started\n")

        name = self.name_prefix + 'server'

        management_network_name = server_config['management_network_name']
        ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'management_network_name': management_network_name,
                'server': {
                    'template': server_config['template'],
                    'cpus': server_config['cpu_count'],
                    'memory': server_config['memory_in_mb']
                },
                'connection_config': {
                    'datacenter_name': server_config['datacenter_name'],
                    'resource_pool_name': server_config['resource_pool_name'],
                    'auto_placement': server_config['auto_placement']
                }
            },
        )

        self.logger.debug("Check there is no server \'{0}\'".format(name))
        self.assertThereIsNoServer(name)
        self.logger.debug("Create server \'{0}\'".format(name))
        server_plugin.create(ctx)
        self.logger.debug("Check server \'{0}\' is created".format(name))
        server = self.assertThereIsOneServerAndGet(name)
        self.logger.debug("Check server \'{0}\' is started".format(name))
        self.assertServerIsStarted(server)

        self.logger.debug("Stop server \'{0}\'".format(name))
        server_plugin.stop(ctx)
        self.logger.debug("Check server \'{0}\' is stopped".format(name))
        self.assertServerIsStopped(server)

        self.logger.debug("Start server \'{0}\'".format(name))
        server_plugin.start(ctx)
        self.logger.debug("Check server \'{0}\' is started".format(name))
        self.assertServerIsStarted(server)

        wait = WAIT_START
        for attempt in range(1, WAIT_COUNT + 1):
            if self.is_server_guest_running(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' to run guest. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    name, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Shutdown server \'{0}\' guest".format(name))
        server_plugin.shutdown_guest(ctx)
        wait = WAIT_START
        for attempt in range(1, WAIT_COUNT + 1):
            if not self.is_server_guest_running(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' to shutdown guest. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    name, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Check server \'{0}\' guest is stopped".format(name))
        self.assertServerGuestIsStopped(server)
        for attempt in range(1, WAIT_COUNT + 1):
            if self.is_server_stopped(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' is stopped. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    name, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Check server \'{0}\' is stopped".format(name))
        self.assertServerIsStopped(server)

        self.logger.debug("Delete server \'{0}\'".format(name))
        server_plugin.delete(ctx)
        self.logger.debug("Check there is no server \'{0}\'".format(name))
        self.assertThereIsNoServer(name)
        self.logger.debug("\nServer test finished\n")

    def test_server_with_network(self):
        self.logger.debug("\nServer test with network started\n")

        name = self.name_prefix + 'server_with_net'

        vswitch_name = server_config['vswitch_name']
        test_networks = server_config['test_networks']

        capabilities = {}

        self.logger.debug("Create test networks")
        for i, net in enumerate(test_networks):
            self.create_network(
                self.name_prefix + net['name'],
                net['vlan_id'],
                vswitch_name
            )
            capabilities['related_network_' + str(i)] =\
                {'node_id': self.name_prefix + net['name']}

        context_capabilities = ContextCapabilities(capabilities)

        management_network_name = server_config['management_network_name']
        ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'management_network_name': management_network_name,
                'server': {
                    'template': server_config['template'],
                    'cpus': server_config['cpu_count'],
                    'memory': server_config['memory_in_mb']
                },
                'connection_config': {
                    'datacenter_name': server_config['datacenter_name'],
                    'resource_pool_name': server_config['resource_pool_name'],
                    'auto_placement': server_config['auto_placement']
                }
            },
            capabilities=context_capabilities
        )

        self.logger.debug("Check there is no server \'{0}\'".format(name))
        self.assertThereIsNoServer(name)
        self.logger.debug("Create server \'{0}\'".format(name))
        server_plugin.create(ctx)
        self.logger.debug("Check server \'{0}\' is created".format(name))
        server = self.assertThereIsOneServerAndGet(name)
        self.logger.debug("Check server \'{0}\' connected networks"
                          .format(name))
        self.assertEquals(len(test_networks)+1, len(server.network))
        self.logger.debug("\nServer test with network finished\n")


if __name__ == '__main__':
    unittest.main()
