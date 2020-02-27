# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

from mock import Mock, patch

from cloudify.exceptions import NonRecoverableError, OperationRetry
from cloudify.state import current_ctx
from cloudify.manager import DirtyTrackingDict
from cloudify.mocks import MockCloudifyContext

from vsphere_storage_plugin import storage


class VsphereStorageTest(unittest.TestCase):

    def setUp(self):
        super(VsphereStorageTest, self).setUp()
        self.mock_ctx = MockCloudifyContext(
            'node_name',
            properties={},
            runtime_properties={}
        )
        self.mock_ctx.instance._runtime_properties = DirtyTrackingDict({})
        self.mock_ctx._operation = Mock()
        self.mock_ctx._capabilities = Mock()
        current_ctx.set(self.mock_ctx)

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_create(self, mock_client_get):
        mock_client_get().create_storage.side_effect = [(
            'file name',
            'something'
        )]
        self.mock_ctx.capabilities.get_all = Mock(return_value={
            'vm_inst_id': {
                'name': 'Julie',
                'vsphere_server_id': 'i',
            },
        })

        storage.create(
            storage={
                'storage_size': 7,
            }, use_external_resource=False)

        self.assertEqual(self.mock_ctx.instance.runtime_properties,
                         {'scsi_id': 'something',
                          'datastore_file_name': 'file name',
                          'attached_vm_id': 'i',
                          'attached_vm_name': 'Julie'})

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_create_ignore(self, mock_client_get):
        runtime = self.mock_ctx.instance.runtime_properties
        runtime['scsi_id'] = 'something'
        runtime['datastore_file_name'] = 'file name'
        runtime['storage_image'] = 'file name'
        runtime['attached_vm_id'] = 'i'
        runtime['attached_vm_name'] = 'Julie'

        self.mock_ctx.capabilities.get_all = Mock(return_value={
            'vm_inst_id': {
                'name': 'Julie',
                'vsphere_server_id': 'i',
            },
        })

        storage.create(
            storage={
                'storage_size': 7,
            }, use_external_resource=False)

        mock_client_get().create_storage.assert_not_called()
        self.assertEqual(self.mock_ctx.instance.runtime_properties,
                         {'scsi_id': 'something',
                          'datastore_file_name': 'file name',
                          'storage_image': 'file name',
                          'attached_vm_id': 'i',
                          'attached_vm_name': 'Julie'})

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_create_race_retry(self, mock_client_get):
        mock_client_get().create_storage.side_effect = NonRecoverableError(
            'vim.fault.FileAlreadyExists')
        self.mock_ctx.capabilities.get_all = Mock(return_value={
            'vm_inst_id': {
                'name': 'Julie',
                'vsphere_server_id': 'i',
            },
        })

        with self.assertRaisesRegexp(
            OperationRetry,
            'Name clash with another storage. Retrying'
        ):
            storage.create(
                storage={
                    'storage_size': 7,
                }, use_external_resource=False)

        self.assertEqual(self.mock_ctx.instance.runtime_properties, {})


if __name__ == '__main__':
    unittest.main()
