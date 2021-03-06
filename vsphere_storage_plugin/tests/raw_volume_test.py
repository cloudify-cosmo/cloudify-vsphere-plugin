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

from cloudify.state import current_ctx
from cloudify.exceptions import NonRecoverableError

import vsphere_plugin_common


class RawVolumeTest(unittest.TestCase):

    def setUp(self):
        super(RawVolumeTest, self).setUp()
        self.mock_ctx = Mock()
        current_ctx.set(self.mock_ctx)

    def test_delete_file_id(self):
        client = vsphere_plugin_common.RawVolumeClient()
        datacenter = Mock()
        client._get_obj_by_id = Mock(return_value=datacenter)
        client.si = Mock()
        # check delete code
        client.delete_file(datacenter_id="datacenter",
                           datastorepath="[datastore] filename")
        # checks
        client._get_obj_by_id.assert_called_once_with(
            vsphere_plugin_common.clients.vim.Datacenter, "datacenter")
        client.si.content.fileManager.DeleteFile.assert_called_once_with(
            '[datastore] filename', datacenter.obj)
        # no such datacenter
        client._get_obj_by_id = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.delete_file(datacenter_id="datacenter",
                               datastorepath="[datastore] filename")

    def test_delete_file_name(self):
        client = vsphere_plugin_common.RawVolumeClient()
        datacenter = Mock()
        client._get_obj_by_name = Mock(return_value=datacenter)
        client.si = Mock()
        # check delete code
        client.delete_file(datacenter_name="datacenter",
                           datastorepath="[datastore] filename")
        # checks
        client._get_obj_by_name.assert_called_once_with(
            vsphere_plugin_common.clients.vim.Datacenter, "datacenter")
        client.si.content.fileManager.DeleteFile.assert_called_once_with(
            '[datastore] filename', datacenter.obj)
        # no such datacenter
        client._get_obj_by_name = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.delete_file(datacenter_name="datacenter",
                               datastorepath="[datastore] filename")

    def test_upload_file(self):
        client = vsphere_plugin_common.RawVolumeClient()
        datacenter = Mock()
        datacenter.name = "datacenter"
        datacenter.id = "datacenter_id"
        client._get_obj_by_name = Mock(return_value=datacenter)
        datastore = Mock()
        datastore.name = "datastore"
        datastore.id = "datastore_id"
        client._get_datastores = Mock(return_value=[datastore])
        client.si = Mock()
        client.si._stub.cookie = ('vmware_soap_session="'
                                  'abcd"; Path=/; HttpOnly; Secure;')
        put_mock = Mock()
        with patch("vsphere_plugin_common.clients.storage.requests.put",
                   put_mock):
            # check upload code
            self.assertEqual(
                client.upload_file(datacenter_name="datacenter",
                                   allowed_datastores=["datastore"],
                                   allowed_datastore_ids=[],
                                   remote_file="file",
                                   data="data",
                                   host="host",
                                   port=80),
                (datacenter.id, '[datastore] file')
            )
        # checks
        put_mock.assert_called_once_with(
            'https://host:80/folder/file',
            cookies={
                'vmware_soap_session': ' "abcd"; $Path=/'
            },
            data='data',
            headers={
                'Content-Type': 'application/octet-stream'
            },
            params={
                'dcPath': "datacenter",
                'dsName': 'datastore'
            },
            verify=False)
        client._get_obj_by_name.assert_called_once_with(
            vsphere_plugin_common.clients.vim.Datacenter, "datacenter")
        client._get_datastores.assert_called_once_with()

        # check by id
        put_mock = Mock()
        with patch("vsphere_plugin_common.clients.storage.requests.put",
                   put_mock):
            # check upload code
            self.assertEqual(
                client.upload_file(datacenter_name="datacenter",
                                   allowed_datastores=[],
                                   allowed_datastore_ids=["datastore_id"],
                                   remote_file="file",
                                   data="data",
                                   host="host",
                                   port=80),
                (datacenter.id, '[datastore] file')
            )

        # without specific datastore
        put_mock = Mock()
        with patch("vsphere_plugin_common.clients.storage.requests.put",
                   put_mock):
            # check upload code
            self.assertEqual(
                client.upload_file(datacenter_name="datacenter",
                                   allowed_datastores=[],
                                   allowed_datastore_ids=[],
                                   remote_file="file",
                                   data="data",
                                   host="host",
                                   port=80),
                (datacenter.id, '[datastore] file')
            )
        put_mock.assert_called_once_with(
            'https://host:80/folder/file',
            cookies={
                'vmware_soap_session': ' "abcd"; $Path=/'
            },
            data='data',
            headers={
                'Content-Type': 'application/octet-stream'
            },
            params={
                'dcPath': "datacenter",
                'dsName': 'datastore'
            },
            verify=False)

        # unknown datastores
        client._get_datastores = Mock(return_value=[])
        with self.assertRaises(NonRecoverableError):
            client.upload_file(datacenter_name="datacenter",
                               allowed_datastores=["datastore"],
                               allowed_datastore_ids=[],
                               remote_file="file",
                               data="data",
                               host="host",
                               port=80)

        # unknown datacenter
        client._get_obj_by_name = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.upload_file(datacenter_name="datacenter",
                               allowed_datastores=["datastore"],
                               allowed_datastore_ids=[],
                               remote_file="file",
                               data="data",
                               host="host",
                               port=80)


if __name__ == '__main__':
    unittest.main()
