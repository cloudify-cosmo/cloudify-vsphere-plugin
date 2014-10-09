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
from vsphere_plugin_common import (TestCase,
                                   TestsConfig)
import server_plugin.server

import socket
import time

from cloudify.context import ContextCapabilities
from cloudify.mocks import MockCloudifyContext


WAIT_START = 10
WAIT_FACTOR = 2
WAIT_COUNT = 6


_tests_config = TestsConfig().get()
server_config = _tests_config['server_test']


class VsphereServerTest(TestCase):

    def setUp(self):
        super(VsphereServerTest, self).setUp()

        name = self.name_prefix + 'server'

        self.ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'networking': server_config["networking"],
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
        ctx_patch = mock.patch('server_plugin.server.ctx', self.ctx)
        ctx_patch.start()
        self.addCleanup(ctx_patch.stop())

    def test_server_create_delete(self):
        self.assertThereIsNoServer(self.ctx.node_id)
        server_plugin.server.start(self.ctx)
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertServerIsStarted(server)

        server_plugin.server.delete(self.ctx)
        self.assertThereIsNoServer(self.ctx.node_id)

    def test_server_start_stop(self):
        server_plugin.server.start(self.ctx)
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertServerIsStarted(server)

        server_plugin.server.stop(self.ctx)
        self.assertServerIsStopped(server)

        server_plugin.server.start(self.ctx)
        self.assertServerIsStarted(server)

    def test_server_shutdown_guest(self):
        server_plugin.server.start(self.ctx)
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertServerIsStarted(server)

        wait = WAIT_START
        for attempt in range(1, WAIT_COUNT + 1):
            if self.is_server_guest_running(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' to run guest. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    self.ctx.node_id, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Shutdown server \'{0}\' guest"
                          .format(self.ctx.node_id))
        server_plugin.server.shutdown_guest()
        wait = WAIT_START
        for attempt in range(1, WAIT_COUNT + 1):
            if not self.is_server_guest_running(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' to shutdown guest. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    self.ctx.node_id, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Check server \'{0}\' guest is stopped"
                          .format(self.ctx.node_id))
        self.assertServerGuestIsStopped(server)
        for attempt in range(1, WAIT_COUNT + 1):
            if self.is_server_stopped(server):
                break
            self.logger.debug(
                "Waiting for server \'{0}\' is stopped. "
                "Attempt #{1}, sleeping for {2} seconds".format(
                    self.ctx.node_id, attempt, wait))
            time.sleep(wait)
            wait *= WAIT_FACTOR
        self.logger.debug("Check server \'{0}\' is stopped"
                          .format(self.ctx.node_id))
        self.assertServerIsStopped(server)

    def test_server_with_public_ip(self):
        server_plugin.server.start(self.ctx)
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertServerIsStarted(server)
        self.assertTrue(server_plugin.server.PUBLIC_IP
                        in self.ctx.runtime_properties)
        ip_valid = True
        try:
            socket.inet_aton(
                self.ctx.runtime_properties[server_plugin.server.PUBLIC_IP])
        except socket.error:
            ip_valid = False
        self.assertTrue(ip_valid)

    def test_server_resize_up(self):
        old_cpus = self.ctx.properties['server']['cpus']
        old_memory = self.ctx.properties['server']['memory']
        new_cpus = old_cpus + 1
        new_memory = old_memory + 64

        server_plugin.server.start()
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertEqual(old_cpus, server.config.hardware.numCPU)
        self.assertEqual(old_memory, server.config.hardware.memoryMB)
        self.ctx.runtime_properties['cpus'] = new_cpus
        self.ctx.runtime_properties['memory'] = new_memory

        server_plugin.server.stop()

        server_plugin.server.resize()

        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertEqual(new_cpus, server.config.hardware.numCPU)
        self.assertEqual(new_memory, server.config.hardware.memoryMB)

    def test_server_resize_down(self):
        old_cpus = self.ctx.properties['server']['cpus']
        self.assertTrue(
            old_cpus > 1,
            "To test server shrink we need more than 1 cpu predefined")
        old_memory = self.ctx.properties['server']['memory']
        new_cpus = old_cpus - 1
        new_memory = old_memory - 64

        server_plugin.server.start()
        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertEqual(old_cpus, server.config.hardware.numCPU)
        self.assertEqual(old_memory, server.config.hardware.memoryMB)
        self.ctx.runtime_properties['cpus'] = new_cpus
        self.ctx.runtime_properties['memory'] = new_memory

        server_plugin.server.stop()

        server_plugin.server.resize()

        server = self.assertThereIsOneServerAndGet(self.ctx.node_id)
        self.assertEqual(new_cpus, server.config.hardware.numCPU)
        self.assertEqual(new_memory, server.config.hardware.memoryMB)

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

        endpoint = None
        context_capabilities = ContextCapabilities(endpoint, capabilities)

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
