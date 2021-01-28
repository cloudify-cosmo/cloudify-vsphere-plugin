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
from cloudify.mocks import MockCloudifyContext

from vsphere_plugin_common.constants import (RESOURCE_POOL_ID,
                                             DELETE_NODE_ACTION)
from cloudify_vsphere import resource_pool


class ResourcePoolTest(unittest.TestCase):

    def setUp(self):
        super(ResourcePoolTest, self).setUp()
        self.mock_ctx = MockCloudifyContext(
            'node_name',
            properties={},
            runtime_properties={}
        )
        self.mock_ctx._operation = Mock()
        current_ctx.set(self.mock_ctx)

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_create(self, mock_client_get):
        vm_resource = Mock()
        vm_resource._moId = 42
        mock_client_get().create_resource_pool.side_effect = [vm_resource]
        self.mock_ctx.node._properties = {
            'connection_config': {
                'host': 'host',
                'port': '80'
            },
            "use_external_resource": False,
            "host_name": "datacenter",
            "name": "test_pool",
            "pool_spec": {
                "cpuAllocation": {
                    "expandableReservation": True,
                    "limit": 2000
                },
                "memoryAllocation": {
                    "expandableReservation": False,
                    "limit": 4096
                }
            }
        }
        resource_pool.create()
        self.assertEqual(self.mock_ctx.instance.runtime_properties,
                         {RESOURCE_POOL_ID: 42})

    @patch('vsphere_plugin_common.VsphereClient.get')
    def test_delete(self, mock_client_get):
        mock_client_get().delete_resource_pool.side_effect = [None]
        self.mock_ctx._operation.name = DELETE_NODE_ACTION
        self.mock_ctx.node.properties['connection_config'] = {
            'host': 'host',
            'port': '80'
        }
        self.mock_ctx.node.properties["name"] = "test_pool"
        self.mock_ctx.instance.runtime_properties[RESOURCE_POOL_ID] = 42
        resource_pool.delete()
        self.assertFalse(self.mock_ctx.instance.runtime_properties)


if __name__ == '__main__':
    unittest.main()
