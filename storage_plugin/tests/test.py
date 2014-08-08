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


__author__ = 'Oleksandr_Raskosov'


import unittest
import storage_plugin.storage as storage_plugin
import vsphere_plugin_common as common

from cloudify.context import ContextCapabilities
from cloudify.mocks import MockCloudifyContext


_tests_config = common.TestsConfig().get()
storage_config = _tests_config['storage_test']


VSPHERE_STORAGE_FILE_NAME = 'vsphere_storage_file_name'


class VsphereStorageTest(common.TestCase):

    def test_storage(self):
        self.logger.debug("\nStorage test started\n")
        name = self.name_prefix + 'stor'

        vm_name = storage_config['vm_name']
        storage_size = int(storage_config['storage_size'])

        capabilities = {}
        capabilities['related_vm'] = {'node_id': vm_name}
        context_capabilities = ContextCapabilities(capabilities)

        ctx = MockCloudifyContext(
            node_id=name,
            properties={
                'storage': {
                    'storage_size': storage_size
                }
            },
            capabilities=context_capabilities
        )

        self.logger.debug(
            "Create storage: VM - \'{0}\', size - {1} GB."
            .format(vm_name, storage_size)
        )
        storage_plugin.create(ctx)

        storage_file_name = ctx[VSPHERE_STORAGE_FILE_NAME]
        self.logger.debug("Check storage \'{0}\' is created"
                          .format(storage_file_name))
        storage = self.assertThereIsStorageAndGet(vm_name, storage_file_name)
        self.logger.debug("Check storage \'{0}\' settings"
                          .format(storage_file_name))
        self.assertEqual(storage_size*1024*1024, storage.capacityInKB)

        self.logger.debug("Delete storage \'{0}\'".format(storage_file_name))
        storage_plugin.delete(ctx)
        self.logger.debug("Check storage \'{0}\' is deleted"
                          .format(storage_file_name))
        self.assertThereIsNoStorage(vm_name, storage_file_name)
        self.logger.debug("\nStorage test finished\n")


if __name__ == '__main__':
    unittest.main()
