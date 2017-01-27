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

import logging
import random
import string
import unittest
import vsphere_plugin_common as vpc
from vsphere_plugin_common.constants import PREFIX_RANDOM_CHARS


class TestsConfig(vpc.Config):
    which = 'unit_tests'


class TestCase(unittest.TestCase):

    def get_server_client(self):
        r = vpc.ServerClient().get()
        self.get_server_client = lambda: r
        return self.get_server_client()

    def get_network_client(self):
        r = vpc.NetworkClient().get()
        self.get_network_client = lambda: r
        return self.get_network_client()

    def setUp(self):
        logger = logging.getLogger(__name__)
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logger
        self.logger.level = logging.DEBUG
        self.logger.debug("VSphere provider test setUp() called")
        chars = string.ascii_uppercase + string.digits
        self.name_prefix = 'vsphere_test_{0}_'\
            .format(''.join(
                random.choice(chars) for x in range(PREFIX_RANDOM_CHARS)))
        self.timeout = 120

        self.logger.debug("VSphere provider test setUp() done")

    def tearDown(self):
        # TODO: Remove all of this, or move it somewhere more sensible.
        # This file claims to be running unit tests, so it should not be
        # making any connections to the outside world.
        self.logger.debug("VSphere provider test tearDown() called")
        # Compute
        self.logger.debug("Check are there any server to delete")
        server_client = self.get_server_client()
        for server in server_client._get_vms():
            server_name = server.name
            if server_name.startswith(self.name_prefix):
                self.logger.debug("Deleting server \"{0}\""
                                  .format(server_name))
                server_client.delete_server(server)
            self.logger.debug("Will not delete server \"{0}\""
                              .format(server_name))
        # Network
        self.logger.debug("Check are there any network to delete")
        network_client = self.get_network_client()
        hosts = network_client.get_host_list()
        for host in hosts:
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                port_group_name = port_group.spec.name
                if port_group_name.startswith(self.name_prefix):
                    self.logger.debug("Deleting Port Group \"{0}\""
                                      " on host \"{1}\""
                                      .format(port_group_name, host.name))
                    network_system.RemovePortGroup(port_group_name)
                self.logger.debug("Will not delete Port Group \"{0}\""
                                  " on host \"{1}\""
                                  .format(port_group_name, host.name))
        self.logger.debug("VSphere provider test tearDown() done")

    @vpc.with_network_client
    def assert_no_port_group(self, name, network_client):
        port_groups = network_client.get_port_group_by_name(name)
        self.assertEqual(0, len(port_groups))

    @vpc.with_network_client
    def assert_port_group_exist_and_get_info(self, name, network_client):
        port_groups = network_client.get_port_group_by_name(name)
        self.assertNotEqual(0, len(port_groups))
        group_name = port_groups[0].spec.name
        group_vlanId = port_groups[0].spec.vlanId
        for port_group in port_groups[1:]:
            self.assertEqual(group_name, port_group.spec.name)
            self.assertEqual(group_vlanId, port_group.spec.vlanId)
        return {'name': group_name, 'vlanId': group_vlanId}

    @vpc.with_server_client
    def assert_no_server(self, name, server_client):
        server = server_client.get_server_by_name(name)
        self.assertIsNone(server)

    @vpc.with_server_client
    def assert_server_exist_and_get(self, name, server_client):
        server = server_client.get_server_by_name(name)
        self.assertIsNotNone(server)
        return server

    @vpc.with_server_client
    def assert_server_started(self, server, server_client):
        self.assertTrue(server_client.is_server_poweredon(server))

    @vpc.with_server_client
    def assert_server_stopped(self, server, server_client):
        self.assertTrue(server_client.is_server_poweredoff(server))

    def assert_server_guest_stopped(self, server):
        self.assertFalse(self.is_server_guest_running(server))

    @vpc.with_server_client
    def is_server_guest_running(self, server, server_client):
        return server_client.is_server_guest_running(server)

    @vpc.with_server_client
    def is_server_stopped(self, server, server_client):
        return server_client.is_server_poweredoff(server)

    @vpc.with_storage_client
    def assert_storage_exists_and_get(
            self, vm_id, storage_file_name, storage_client):
        storage = storage_client.get_storage(vm_id, storage_file_name)
        self.assertIsNotNone(storage)
        return storage

    @vpc.with_storage_client
    def assert_no_storage(self, vm_id, storage_file_name, storage_client):
        storage = storage_client.get_storage(vm_id, storage_file_name)
        self.assertIsNone(storage)


def able_to_connect():
    try:
        vpc.ServerClient().get()
        vpc.NetworkClient().get()
        vpc.StorageClient().get()
    except Exception as e:
        print(str(e))
        return False
    else:
        return True
