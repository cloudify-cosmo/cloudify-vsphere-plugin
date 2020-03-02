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

from vsphere_plugin_common.constants import DELETE_NODE_ACTION
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

        # not provided capabilities
        self.mock_ctx.capabilities.get_all = Mock(return_value={})

        with self.assertRaises(NonRecoverableError):
            storage.create(
                storage={
                    'storage_size': 7,
                }, use_external_resource=False)

        # wrong list capabilities
        self.mock_ctx.capabilities.get_all = Mock(return_value={
            'vm_inst_id': {
                'name': 'Julie',
                'vsphere_server_id': '1',
            },
            'vm_inst_other': {
                'name': 'Julie',
                'vsphere_server_id': '2',
            },
        })

        with self.assertRaises(NonRecoverableError):
            storage.create(
                storage={
                    'storage_size': 7,
                }, use_external_resource=False)

        # correct settings
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
    def test_storage_create_external(self, mock_client_get):
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

        # not enough info
        with self.assertRaises(NonRecoverableError):
            storage.create(
                storage={
                    'storage_size': 7,
                }, use_external_resource=True)

        storage.create(
            storage={
                'scsi_id': 'something',
                'datastore_file_name': 'file name',
                'storage_size': 7,
            }, use_external_resource=True)

        self.assertEqual(self.mock_ctx.instance.runtime_properties,
                         {'datastore_file_name': 'file name',
                          'storage_size': 7,
                          'scsi_id': 'something',
                          'attached_vm_id': 'i',
                          'attached_vm_name': 'Julie',
                          'use_external_resource': True})

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

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_create_race_nonrecovery(self, mock_client_get):
        mock_client_get().create_storage.side_effect = NonRecoverableError(
            'Something is going wrong')
        self.mock_ctx.capabilities.get_all = Mock(return_value={
            'vm_inst_id': {
                'name': 'Julie',
                'vsphere_server_id': 'i',
            },
        })

        with self.assertRaisesRegexp(
            NonRecoverableError,
            'Something is going wrong'
        ):
            storage.create(
                storage={
                    'storage_size': 7,
                }, use_external_resource=False)

        self.assertFalse(self.mock_ctx.instance.runtime_properties)

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_delete(self, mock_client_get):
        self.mock_ctx._operation.name = DELETE_NODE_ACTION
        # skiped delete with empty
        storage.delete()
        mock_client_get().delete_storage.assert_not_called()

        # skiped external
        runtime_properties = self.mock_ctx.instance.runtime_properties
        runtime_properties['datastore_file_name'] = 'file name'
        runtime_properties['storage_size'] = 7
        runtime_properties['scsi_id'] = 'something'
        runtime_properties['attached_vm_id'] = 'i'
        runtime_properties['attached_vm_name'] = 'Julie'
        runtime_properties['use_external_resource'] = True
        storage.delete()
        self.assertFalse(self.mock_ctx.instance.runtime_properties)
        mock_client_get().delete_storage.assert_not_called()

        # remove real storage
        mock_client_get().resize_storage = Mock()
        runtime_properties = self.mock_ctx.instance.runtime_properties
        runtime_properties['scsi_id'] = 'something'
        runtime_properties['datastore_file_name'] = 'file name'
        runtime_properties['attached_vm_id'] = 'i'
        runtime_properties['attached_vm_name'] = 'Julie'
        storage.delete()
        self.assertFalse(self.mock_ctx.instance.runtime_properties)
        mock_client_get().delete_storage.assert_called_with(
            'i', 'file name', instance=self.mock_ctx.instance)

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_resize(self, mock_client_get):
        # skiped delete with empty
        storage.resize()
        mock_client_get().resize_storage.assert_not_called()

        # resize external
        runtime_properties = self.mock_ctx.instance.runtime_properties
        runtime_properties['datastore_file_name'] = 'file name'
        runtime_properties['storage_size'] = 7
        runtime_properties['scsi_id'] = 'something'
        runtime_properties['attached_vm_id'] = 'i'
        runtime_properties['attached_vm_name'] = 'Julie'
        runtime_properties['use_external_resource'] = True
        storage.resize()
        self.assertEqual(self.mock_ctx.instance.runtime_properties, {
            'datastore_file_name': 'file name',
            'storage_size': 7,
            'scsi_id': 'something',
            'attached_vm_id': 'i',
            'attached_vm_name': 'Julie',
            'use_external_resource': True})
        mock_client_get().resize_storage.assert_called_with(
            'i', 'file name', 7, instance=self.mock_ctx.instance)

        # resize real storage
        runtime_properties = self.mock_ctx.instance.runtime_properties
        runtime_properties['scsi_id'] = 'something'
        runtime_properties['datastore_file_name'] = 'file name'
        runtime_properties['attached_vm_id'] = 'i'
        runtime_properties['attached_vm_name'] = 'Julie'
        storage.resize()
        self.assertEqual(self.mock_ctx.instance.runtime_properties, {
            'datastore_file_name': 'file name',
            'storage_size': 7,
            'scsi_id': 'something',
            'attached_vm_id': 'i',
            'attached_vm_name': 'Julie',
            'use_external_resource': True})

        # resize to zero
        runtime_properties = self.mock_ctx.instance.runtime_properties
        runtime_properties['scsi_id'] = 'something'
        runtime_properties['datastore_file_name'] = 'file name'
        runtime_properties['attached_vm_id'] = 'i'
        runtime_properties['attached_vm_name'] = 'Julie'
        runtime_properties['storage_size'] = 0
        with self.assertRaises(NonRecoverableError):
            storage.resize()


if __name__ == '__main__':
    unittest.main()
