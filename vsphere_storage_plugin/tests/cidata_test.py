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

from vsphere_storage_plugin import cidata


class VsphereCIDataTest(unittest.TestCase):

    def setUp(self):
        super(VsphereCIDataTest, self).setUp()
        self.mock_ctx = Mock()
        current_ctx.set(self.mock_ctx)

    def test_joliet_name(self):
        self.assertEqual("/abc", cidata._joliet_name("abc"))
        self.assertEqual("/" + "*" * 64, cidata._joliet_name("*" * 128))
        self.assertEqual("/" + "*" * 64,
                         cidata._joliet_name("/" + "*" * 128))

    def test_iso_name(self):
        self.assertEqual("/ABC.;3", cidata._iso_name("abc"))
        self.assertEqual("/1234567890_ABCDEF.;3",
                         cidata._iso_name("1234567890.abcdef"))
        self.assertEqual("/" + "_" * 16 + ".;3",
                         cidata._iso_name("*" * 16))
        self.assertEqual("/" + "_" * 16 + ".;3",
                         cidata._iso_name("/" + "*" * 16))
        self.assertEqual("/12345678.123;3",
                         cidata._iso_name("12345678.123"))

    def test_create_iso(self):
        _get_resource = Mock(return_value="abc")
        cidata._create_iso(
            vol_ident='vol', sys_ident='sys', files={
                "a/b/c": "d",
                'c': 'f'
            }, raw_files={
                'g': 'file_call'
            }, get_resource=_get_resource)
        _get_resource.assert_called_once_with('file_call')

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_create(self, mock_client_get):
        mock_client_get().upload_file.side_effect = ['[storage] check']
        self.mock_ctx.get_resource = Mock(return_value="abc")
        self.mock_ctx.instance.runtime_properties = {}
        self.mock_ctx.node.properties = {
            'connection_config': {
                'host': 'host',
                'port': '80'
            }
        }

        cidata.create(
            files=None, raw_files={
                'g': 'file_call'
            }, datacenter_name='datacenter', allowed_datastores=['abc'],
            vol_ident="vol", sys_ident="sys", volume_prefix="abc")

        self.mock_ctx.operation.retry.assert_not_called()
        self.assertEqual(
            self.mock_ctx.instance.runtime_properties,
            {'storage_image': '[storage] check'}
        )

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_storage_delete(self, mock_client_get):
        # delete volume
        self.mock_ctx.get_resource = Mock(return_value="abc")
        self.mock_ctx.instance.runtime_properties = {
            'storage_image': '[storage] check'}
        self.mock_ctx.node.properties = {}

        cidata.delete(datacenter_name='datacenter')
        self.mock_ctx.operation.retry.assert_not_called()
        self.assertEqual(
            self.mock_ctx.instance.runtime_properties,
            {'storage_image': None}
        )
        # already deleted volume
        cidata.delete(datacenter_name='datacenter')
        self.mock_ctx.operation.retry.assert_not_called()
        self.assertEqual(
            self.mock_ctx.instance.runtime_properties,
            {'storage_image': None}
        )


if __name__ == '__main__':
    unittest.main()
