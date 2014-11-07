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
import server_plugin.server as server_plugin
import storage_plugin.storage as storage_plugin
import vsphere_plugin_common as common

from cloudify.context import ContextCapabilities
from cloudify.mocks import MockCloudifyContext


_tests_config = common.TestsConfig().get()
storage_config = _tests_config['storage_test']


VSPHERE_STORAGE_FILE_NAME = 'vsphere_storage_file_name'


class VsphereStorageTest(common.TestCase):

    def setUp(self):
        super(VsphereStorageTest, self).setUp()
        self.logger.debug("\nStorage test started\n")
        name = self.name_prefix + 'stor'

        vm_name = storage_config['vm_name']
        storage_size = int(storage_config['storage_size'])

        server_client = common.ServerClient().get()
        vm = server_client.get_server_by_name(vm_name)
        capability = {server_plugin.VSPHERE_SERVER_ID: vm._moId}
        endpoint = None
        context_capabilities_m = ContextCapabilities(endpoint)
        get_all_m = mock.Mock()
        get_all_m.values = mock.Mock(return_value=[capability])
        context_capabilities_m.get_all = mock.Mock(return_value=get_all_m)

        self.ctx = MockCloudifyContext(
            node_id=name,
            node_name=name,
            properties={
                'storage': {
                    'storage_size': storage_size
                }
            },
            capabilities=context_capabilities_m
        )
        ctx_patch1 = mock.patch('storage_plugin.storage.ctx', self.ctx)
        ctx_patch1.start()
        self.addCleanup(ctx_patch1.stop)
        ctx_patch2 = mock.patch('vsphere_plugin_common.ctx', self.ctx)
        ctx_patch2.start()
        self.addCleanup(ctx_patch2.stop)

    def tearDown(self):
        try:
            storage_plugin.delete()
        except Exception:
            pass
        super(VsphereStorageTest, self).tearDown()

    def test_storage_create_delete(self):
        storage_size = self.ctx.node.properties['storage']['storage_size']
        vm_id = self.ctx.capabilities.get_all().values()[0][
            server_plugin.VSPHERE_SERVER_ID]

        storage_plugin.create()

        storage_file_name = \
            self.ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]
        self.logger.debug("Check storage \'{0}\' is created"
                          .format(storage_file_name))
        storage = self.assertThereIsStorageAndGet(vm_id, storage_file_name)
        self.logger.debug("Check storage \'{0}\' settings"
                          .format(storage_file_name))
        self.assertEqual(storage_size*1024*1024, storage.capacityInKB)

        self.logger.debug("Delete storage \'{0}\'".format(storage_file_name))
        storage_plugin.delete()
        self.logger.debug("Check storage \'{0}\' is deleted"
                          .format(storage_file_name))
        self.assertThereIsNoStorage(vm_id, storage_file_name)

    def test_storage_resize(self):
        vm_id = self.ctx.capabilities.get_all().values()[0][
            server_plugin.VSPHERE_SERVER_ID]
        storage_size = self.ctx.node.properties['storage']['storage_size']
        new_storage_size = storage_size + 1

        storage_plugin.create()

        self.ctx.instance.runtime_properties['storage_size'] = new_storage_size

        storage_plugin.resize()

        storage_file_name = \
            self.ctx.instance.runtime_properties[VSPHERE_STORAGE_FILE_NAME]

        storage = self.assertThereIsStorageAndGet(vm_id, storage_file_name)
        self.assertEqual(new_storage_size*1024*1024, storage.capacityInKB)
