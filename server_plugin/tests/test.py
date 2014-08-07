__author__ = 'Oleksandr_Raskosov'


import unittest
from vsphere_plugin_common import (TestCase,
                                   TestsConfig)
import server_plugin.server

import time

from cloudify.context import ContextCapabilities
from cloudify.mocks import MockCloudifyContext


WAIT_START = 10
WAIT_FACTOR = 2
WAIT_COUNT = 6


_tests_config = TestsConfig().get()
server_config = _tests_config['server_test']


class VsphereServerTest(TestCase):

    def test_server(self):
        self.logger.debug("\nServer test started\n")

        name = self.name_prefix + 'server'

        networking = server_config["networking"]
        use_dhcp = networking['use_dhcp']
        management_network = networking['management_network']
        management_network_name = management_network['name']
        networking_properties = None
        if use_dhcp:
            networking_properties = {
                'use_dhcp': use_dhcp,
                'management_network': {
                    'name': management_network_name
                }
            }
        else:
            networking_properties = {
                'use_dhcp': use_dhcp,
                'domain': networking['domain'],
                'dns_servers': networking['dns_servers'],
                'management_network': {
                    'name': management_network_name,
                    'network': management_network['network'],
                    'gateway': management_network['gateway'],
                    'ip': management_network['ip']
                }
            }
        ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'networking': networking_properties,
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
        server_plugin.server.start(ctx)
        self.logger.debug("Check server \'{0}\' is created".format(name))
        server = self.assertThereIsOneServerAndGet(name)
        self.logger.debug("Check server \'{0}\' is started".format(name))
        self.assertServerIsStarted(server)

        self.logger.debug("Stop server \'{0}\'".format(name))
        server_plugin.server.stop(ctx)
        self.logger.debug("Check server \'{0}\' is stopped".format(name))
        self.assertServerIsStopped(server)

        self.logger.debug("Start server \'{0}\'".format(name))
        server_plugin.server.start(ctx)
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
        server_plugin.server.shutdown_guest(ctx)
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
        server_plugin.server.delete(ctx)
        self.logger.debug("Check there is no server \'{0}\'".format(name))
        self.assertThereIsNoServer(name)
        self.logger.debug("\nServer test finished\n")

    @unittest.skip("not changed yet")
    def test_server_with_network(self):
        self.logger.debug("\nServer test with network started\n")

        name = self.name_prefix + 'server_with_net'

        networking = server_config["networking"]
        use_dhcp = networking['use_dhcp']
        vswitch_name = server_config['vswitch_name']
        test_networks = networking['test_networks']

        capabilities = {}

        self.logger.debug("Create test networks")
        for i, net in enumerate(test_networks):
            self.create_network(
                self.name_prefix + net['name'],
                net['vlan_id'],
                vswitch_name
            )
            if use_dhcp:
                capabilities['related_network_' + str(i)] =\
                    {'node_id': self.name_prefix + net['name']}
            else:
                capabilities['related_network_' + str(i)] = {
                    'node_id': self.name_prefix + net['name'],
                    'network': net['network'],
                    'gateway': net['gateway'],
                    'ip': net['ip']
                }

        context_capabilities = ContextCapabilities(capabilities)

        management_network = networking['management_network']
        management_network_name = management_network['name']
        networking_properties = None
        if use_dhcp:
            networking_properties = {
                'use_dhcp': use_dhcp,
                'management_network': {
                    'name': management_network_name
                }
            }
        else:
            networking_properties = {
                'use_dhcp': use_dhcp,
                'domain': networking['domain'],
                'dns_servers': networking['dns_servers'],
                'management_network': {
                    'name': management_network_name,
                    'network': management_network['network'],
                    'gateway': management_network['gateway'],
                    'ip': management_network['ip']
                }
            }
        ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'networking': networking_properties,
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
        server_plugin.server.create(ctx)
        self.logger.debug("Check server \'{0}\' is created".format(name))
        server = self.assertThereIsOneServerAndGet(name)
        self.logger.debug("Check server \'{0}\' connected networks"
                          .format(name))
        self.assertEquals(len(test_networks)+1, len(server.network))
        self.logger.debug("\nServer test with network finished\n")


if __name__ == '__main__':
    unittest.main()
