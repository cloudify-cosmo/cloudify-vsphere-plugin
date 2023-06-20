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
from pyVmomi import vim

from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext

from vsphere_plugin_common.constants import DELETE_NODE_ACTION
import cloudify_vsphere.contentlibrary.deployment as deployment


class ContentDeploymentTest(unittest.TestCase):

    def setUp(self):
        super(ContentDeploymentTest, self).setUp()
        self.mock_ctx = MockCloudifyContext(
            'node_name',
            properties={
                "connection_config": {
                    "username": "vcenter_user",
                    "password": "vcenter_password",
                    "host": "vcenter_ip",
                    "port": 443,
                    "datacenter_name": "vcenter_datacenter",
                    "resource_pool_name": "vcenter_resource_pool",
                    "auto_placement": "vsphere_auto_placement",
                    "allow_insecure": True
                }
            },
            runtime_properties={}
        )
        self.mock_ctx._execution_id = "execution_id"
        self.mock_ctx._operation = Mock()
        self.mock_ctx._capabilities = Mock()
        current_ctx.set(self.mock_ctx)

    @patch("vsphere_plugin_common.clients.SmartConnectNoSSL")
    @patch('vsphere_plugin_common.clients.Disconnect', Mock())
    def test_delete(self, smart_m):
        conn_mock = Mock()
        smart_m.return_value = conn_mock
        ctx = self.mock_ctx
        ctx._operation.name = DELETE_NODE_ACTION

        runtime_properties = ctx.instance.runtime_properties
        runtime_properties[deployment.CONTENT_ITEM_ID] = 'item'
        runtime_properties[deployment.CONTENT_LIBRARY_ID] = 'library'
        runtime_properties[deployment.VSPHERE_SERVER_ID] = 'server'
        runtime_properties[deployment.CONTENT_LIBRARY_VM_NAME] = 'name'

        vm = Mock()
        task = Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.Destroy = Mock(return_value=task)
        with patch(
            "vsphere_plugin_common.clients.VsphereClient._get_obj_by_id",
            Mock(return_value=vm)
        ):
            deployment.delete(server_client=None,
                              ctx=ctx,
                              max_wait_time=300)
        self.assertFalse(self.mock_ctx.instance.runtime_properties)

    def test_create(self):
        response_login = Mock()
        response_login.cookies = {'vmware-api-session-id': 'session_id'}
        response_login.json = Mock(return_value={"value": 'session_id'})

        response_deployment = Mock()
        response_deployment.cookies = {}
        response_deployment.json = Mock(return_value={"value": {
            'succeeded': True,
            'resource_id': {
                'id': 'deployed'}}})

        response_item_list = Mock()
        response_item_list.cookies = {}
        response_item_list.json = Mock(return_value={"value": ['abc']})

        response_item = Mock()
        response_item.cookies = {}
        response_item.json = Mock(return_value={"value": {'name': 'def',
                                                'id': 'id_def'}})

        response_library_list = Mock()
        response_library_list.cookies = {}
        response_library_list.json = Mock(return_value={"value": ['abc']})

        response_library = Mock()
        response_library.cookies = {}
        response_library.json = Mock(return_value={"value": {'name': 'abc',
                                                   'id': 'id_abc'}})

        response_logout = Mock()
        response_logout.cookies = {}
        response_logout.json = Mock(return_value={"value": "closed"})

        _responses = [response_logout,
                      response_deployment,
                      response_deployment,
                      response_item,
                      response_item_list,
                      response_library,
                      response_library_list,
                      response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        type_vsphere = 'cloudify.vsphere.nodes.ContentLibraryDeployment'
        self.mock_ctx.node._type = type_vsphere

        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            deployment.create(ctx=self.mock_ctx,
                              connection_config={'host': 'host',
                                                 'username': 'username',
                                                 'password': 'password',
                                                 'allow_insecure': True},
                              library_name="abc",
                              template_name="def",
                              target={'target': '_target'},
                              deployment_spec={'param': '_param'})
        self.assertEqual(
            self.mock_ctx.instance.runtime_properties,
            {'vm_name': 'node-name',
             'vsphere_server_id': 'deployed',
             'content_item_id': 'id_def',
             'content_library_id': 'id_abc'})

        # check rerun
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            deployment.create(ctx=self.mock_ctx,
                              connection_config={'host': 'host',
                                                 'username': 'username',
                                                 'password': 'password',
                                                 'allow_insecure': True},
                              library_name="abc",
                              template_name="def",
                              target={'target': '_target'},
                              deployment_spec={'param': '_param'})


if __name__ == '__main__':
    unittest.main()
