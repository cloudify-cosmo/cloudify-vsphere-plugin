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

from vsphere_network_plugin import ippool


class IPPoolTest(unittest.TestCase):

    def setUp(self):
        super(IPPoolTest, self).setUp()
        self.mock_ctx = Mock()
        current_ctx.set(self.mock_ctx)

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_create(self, mock_client_get):
        mock_client_get().create_ippool.side_effect = [12345]
        self.mock_ctx.instance.runtime_properties = {}
        rel = Mock()
        rel.type_hierarchy = [
            "cloudify.relationships.vsphere.ippool_connected_to_network"]
        rel.target.node.type_hierarchy = ["cloudify.vsphere.nodes.Network"]
        self.mock_ctx.instance.relationships = [rel]
        self.mock_ctx.node.properties = {
            'connection_config': {
                'host': 'host',
                'port': '80'
            },
            "datacenter_name": "datacenter",
            "ippool": {
                "name": "ippool-check",
                "subnet": "192.0.2.0",
                "netmask": "255.255.255.0",
                "gateway": "192.0.2.254",
                "range": "192.0.2.1#12"
            }
        }

        ippool.create()
        self.mock_ctx.operation.retry.assert_not_called()
        self.assertEqual(
            self.mock_ctx.instance.runtime_properties,
            {'ippool': 12345}
        )
        mock_client_get().create_ippool.assert_called_once_with(
            'datacenter', {
                'subnet': '192.0.2.0',
                'netmask': '255.255.255.0',
                'range': '192.0.2.1#12',
                'name': 'ippool-check',
                'gateway': '192.0.2.254'
            },
            [rel.target.instance])

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_delete(self, mock_client_get):
        mock_client_get().delete_ippool.side_effect = [None]
        self.mock_ctx.instance.runtime_properties = {}
        self.mock_ctx.node.properties = {
            'connection_config': {
                'host': 'host',
                'port': '80'
            },
            "datacenter_name": "datacenter"
        }
        # nothing to remove
        ippool.delete()
        self.assertFalse(self.mock_ctx.instance.runtime_properties)
        # something exists
        self.mock_ctx.instance.runtime_properties = {'ippool': 12345}
        ippool.delete()
        mock_client_get().delete_ippool.assert_called_once_with(
            'datacenter', 12345)
        self.assertFalse(self.mock_ctx.instance.runtime_properties)


if __name__ == '__main__':
    unittest.main()
