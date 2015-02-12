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
from vsphere_plugin_common import (TestCase,
                                   TestsConfig)
import server_plugin.server

import socket
import time

from cloudify.mocks import MockCloudifyContext

WAIT_TIMEOUT = 10
WAIT_COUNT = 20

_tests_config = TestsConfig().get()
server_config = _tests_config['server_test']


class VsphereServerTest(TestCase):

    def setUp(self):
        super(VsphereServerTest, self).setUp()

        name = self.name_prefix + 'server'

        self.ctx = MockCloudifyContext(
            node_id=name,
            node_name=name,
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
            bootstrap_context=mock.Mock()
        )
        self.ctx.bootstrap_context.resources_prefix = ''
        ctx_patch1 = mock.patch('server_plugin.server.ctx', self.ctx)
        ctx_patch1.start()
        self.addCleanup(ctx_patch1.stop)
        ctx_patch2 = mock.patch('vsphere_plugin_common.ctx', self.ctx)
        ctx_patch2.start()
        self.addCleanup(ctx_patch2.stop)

    def test_server_create_delete(self):
        self.assert_no_server(self.ctx.node.id)
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

        server_plugin.server.delete()
        self.assert_no_server(self.ctx.node.id)

    def test_server_start_stop(self):
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

        server_plugin.server.stop()
        self.assert_server_stopped(server)

        server_plugin.server.start()
        self.assert_server_started(server)

    def test_server_shutdown_guest(self):
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

        for _ in range(WAIT_COUNT):
            if self.is_server_guest_running(server):
                break
            time.sleep(WAIT_TIMEOUT)

        server_plugin.server.shutdown_guest()

        for _ in range(WAIT_COUNT):
            if not self.is_server_guest_running(server):
                break
            time.sleep(WAIT_TIMEOUT)

        self.assert_server_guest_stopped(server)
        for _ in range(WAIT_COUNT):
            if self.is_server_stopped(server):
                break
            time.sleep(WAIT_TIMEOUT)

        self.assert_server_stopped(server)

    def test_server_with_public_ip(self):
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

        get_state_verified = False
        for _ in range(WAIT_COUNT):
            if server_plugin.server.get_state():
                get_state_verified = True
                break
            time.sleep(WAIT_TIMEOUT)
        self.assertTrue(get_state_verified)

        self.assertTrue(server_plugin.server.PUBLIC_IP
                        in self.ctx.instance.runtime_properties)
        ip = self.ctx.instance.runtime_properties[
            server_plugin.server.PUBLIC_IP]
        ip_valid = True
        try:
            socket.inet_aton(ip)
        except socket.error:
            ip_valid = False
        self.assertTrue(ip_valid)

    def test_server_resize_up(self):
        old_cpus = self.ctx.node.properties['server']['cpus']
        old_memory = self.ctx.node.properties['server']['memory']
        new_cpus = old_cpus + 1
        new_memory = old_memory + 64

        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assertEqual(old_cpus, server.config.hardware.numCPU)
        self.assertEqual(old_memory, server.config.hardware.memoryMB)
        self.ctx.instance.runtime_properties['cpus'] = new_cpus
        self.ctx.instance.runtime_properties['memory'] = new_memory

        server_plugin.server.stop()

        server_plugin.server.resize()

        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assertEqual(new_cpus, server.config.hardware.numCPU)
        self.assertEqual(new_memory, server.config.hardware.memoryMB)

    def test_server_resize_down(self):
        old_cpus = self.ctx.node.properties['server']['cpus']
        self.assertTrue(
            old_cpus > 1,
            "To test server shrink we need more than 1 cpu predefined")
        old_memory = self.ctx.node.properties['server']['memory']
        new_cpus = old_cpus - 1
        new_memory = old_memory - 64

        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assertEqual(old_cpus, server.config.hardware.numCPU)
        self.assertEqual(old_memory, server.config.hardware.memoryMB)
        self.ctx.instance.runtime_properties['cpus'] = new_cpus
        self.ctx.instance.runtime_properties['memory'] = new_memory

        server_plugin.server.stop()

        server_plugin.server.resize()

        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assertEqual(new_cpus, server.config.hardware.numCPU)
        self.assertEqual(new_memory, server.config.hardware.memoryMB)

    def test_get_state(self):
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

        get_state_verified = False
        for _ in range(WAIT_COUNT):
            if server_plugin.server.get_state():
                get_state_verified = True
                break
            time.sleep(WAIT_TIMEOUT)
        self.assertTrue(get_state_verified)

        self.assertTrue('networks' in self.ctx.instance.runtime_properties)
        self.assertTrue('ip' in self.ctx.instance.runtime_properties)
        ip_valid = True
        try:
            socket.inet_aton(self.ctx.instance.runtime_properties['ip'])
        except socket.error:
            ip_valid = False
        self.assertTrue(ip_valid)

    def test_server_create_with_autoplacement(self):
        self.ctx.node.properties['connection_config']['auto_placement'] = True
        self.assert_no_server(self.ctx.node.id)
        server_plugin.server.start()
        server = self.assert_server_exist_and_get(self.ctx.node.id)
        self.assert_server_started(server)

    def test_server_create_with_prefix(self):
        prefix = 'prefix_'
        self.ctx.bootstrap_context.resources_prefix = prefix

        server_plugin.server.start()
        self.addCleanup(server_plugin.server.delete)
        server = self.assert_server_exist_and_get(prefix + self.ctx.node.id)
        self.assert_server_started(server)
