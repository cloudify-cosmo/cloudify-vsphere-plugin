# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
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

import vsphere_plugin_common


class RawVolumeTest(unittest.TestCase):

    def setUp(self):
        super(RawVolumeTest, self).setUp()
        self.mock_ctx = Mock()
        current_ctx.set(self.mock_ctx)

    def test_delete_file(self):
        client = vsphere_plugin_common.RawVolumeClient()
        datacenter = Mock()
        client._get_obj_by_name = Mock(return_value=datacenter)
        client.si = Mock()
        # check delete code
        client.delete_file("datacenter", "[datastore] filename")
        # checks
        client._get_obj_by_name.assert_called_once_with(
            vsphere_plugin_common.vim.Datacenter, "datacenter")
        client.si.content.fileManager.DeleteFile.assert_called_once_with(
            '[datastore] filename', datacenter.obj)

    def test_upload_file(self):
        client = vsphere_plugin_common.RawVolumeClient()
        datacenter = Mock()
        datacenter.name = "datacenter"
        client._get_obj_by_name = Mock(return_value=datacenter)
        datastore = Mock()
        datastore.name = "datastore"
        client._get_datastores = Mock(return_value=[datastore])
        client.si = Mock()
        client.si._stub.cookie = ('vmware_soap_session="'
                                  'abcd"; Path=/; HttpOnly; Secure;')
        put_mock = Mock()
        with patch("vsphere_plugin_common.requests.put", put_mock):
            # check upload code
            self.assertEqual(
                client.upload_file("datacenter", ["datastore"], "file", "data",
                                   "host", 80),
                '[datastore] file'
            )
        # checks
        put_mock.assert_called_once_with(
            'https://host:80/folderfile',
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
            vsphere_plugin_common.vim.Datacenter, "datacenter")
        client._get_datastores.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
