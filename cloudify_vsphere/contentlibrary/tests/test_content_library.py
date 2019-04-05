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
import collections

import unittest

from mock import Mock, patch

from cloudify.state import current_ctx
from cloudify.exceptions import NonRecoverableError

import cloudify_vsphere.contentlibrary as contentlibrary


class ContentLibraryTest(unittest.TestCase):

    def setUp(self):
        super(ContentLibraryTest, self).setUp()
        self.mock_ctx = Mock()
        current_ctx.set(self.mock_ctx)
        # test results
        self.response_login = Mock()
        self.response_login.cookies = {'vmware-api-session-id': 'session_id'}
        self.response_login.json = Mock(return_value={"value": 'session_id'})

        self.response_empty = Mock()
        self.response_empty.cookies = {'vmware-api-session-id': 'session_id'}
        self.response_empty.json = Mock(return_value={"value": []})

        self.response_logout = Mock()
        self.response_logout.cookies = {}
        self.response_logout.json = Mock(return_value={"value": "closed"})

    def test_init(self):
        requests = Mock()
        requests.request = Mock(return_value=self.response_login)
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            # correct session id
            contentlibrary.ContentLibrary({'host': 'host',
                                           'username': 'username',
                                           'password': 'password',
                                           'allow_insecure': True})
            # wrong session id
            response = Mock()
            response.json = Mock(return_value={"value": 'other_id'})
            response.cookies = {'vmware-api-session-id': 'session_id'}
            requests.request = Mock(return_value=response)
            with self.assertRaises(NonRecoverableError):
                contentlibrary.ContentLibrary({'host': 'host',
                                               'username': 'username',
                                               'password': 'password',
                                               'allow_insecure': True})
            # no response
            response = Mock()
            response.json = Mock(return_value={})
            response.cookies = {}
            requests.request = Mock(return_value=response)
            with self.assertRaises(NonRecoverableError):
                contentlibrary.ContentLibrary({'host': 'host',
                                               'username': 'username',
                                               'password': 'password',
                                               'allow_insecure': True})

    def test_content_library_get_fail(self):
        _responses = [self.response_logout,
                      self.response_empty,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check empty content libraries list
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})

            with self.assertRaises(NonRecoverableError):
                cl.content_library_get("abc")

    def test_content_library_get(self):
        response_list = Mock()
        response_list.cookies = {}
        response_list.json = Mock(return_value={"value": ['abc']})

        response_library = Mock()
        response_library.cookies = {}
        response_library.json = Mock(return_value={"value": {'name': 'abc',
                                                             'id': 'id'}})

        _responses = [self.response_logout,
                      response_library,
                      response_list,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check content libraries list
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})

            self.assertEqual(cl.content_library_get("abc"),
                             {'name': 'abc', 'id': 'id'})

    def test_content_item_get_fail(self):
        _responses = [self.response_logout,
                      self.response_empty,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check empty content libraries list
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})

            with self.assertRaises(NonRecoverableError):
                cl.content_item_get("abc", "def")

    def test_content_item_get(self):
        response_list = Mock()
        response_list.cookies = {}
        response_list.json = Mock(return_value={"value": ['abc']})

        response_item = Mock()
        response_item.cookies = {}
        response_item.json = Mock(return_value={"value": {'name': 'def',
                                                'id': 'id'}})

        _responses = [self.response_logout,
                      response_item,
                      response_list,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response

        # check content libraries list
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})

            self.assertEqual(cl.content_item_get("abc", "def"),
                             {'name': 'def', 'id': 'id'})

    def test_cleanup_parmeters(self):
        _responses = [self.response_logout,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check correct deployment
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})
            self.assertEqual(
                cl._cleanup_specs({"additional_parameters": [{
                    "type": "DeploymentOptionParams",
                    "@class": "com.vmware.vcenter.ovf.deployment_option_params"
                }]}),
                {'additional_parameters': [collections.OrderedDict([(
                    # class should be always first in list
                    '@class', 'com.vmware.vcenter.ovf.deployment_option_params'
                ), (
                    'type', 'DeploymentOptionParams'
                )])]}
            )

    def test_content_item_deploy(self):
        response_deployment = Mock()
        response_deployment.cookies = {}
        response_deployment.json = Mock(return_value={"value": {
            'name': 'def',
            'succeeded': True,
            'id': 'id'}})

        response_deployment_state = Mock()
        response_deployment_state.cookies = {}
        response_deployment_state.json = Mock(return_value={"value": {
            'name': 'def',
            'id': 'id'}})

        _responses = [self.response_logout,
                      response_deployment,
                      response_deployment_state,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check correct deployment
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            cl = contentlibrary.ContentLibrary({'host': 'host',
                                                'username': 'username',
                                                'password': 'password',
                                                'allow_insecure': True})

            self.assertEqual(
                cl.content_item_deploy(
                    "abc", {'target': '_target'}, {'param': '_param'}),
                {'name': 'def', 'succeeded': True, 'id': 'id'})

    def test_content_item_deploy_fail(self):
        # failed deployment
        response_deployment_state = Mock()
        response_deployment_state.cookies = {}
        response_deployment_state.json = Mock(return_value={"value": {
            'name': 'def',
            'id': 'id'}})

        response_failed_deployment = Mock()
        response_failed_deployment.cookies = {}
        response_failed_deployment.json = Mock(return_value={"value": {
            'name': 'def',
            'succeeded': False,
            'id': 'id'}})

        _responses = [self.response_logout,
                      response_failed_deployment,
                      response_deployment_state,
                      self.response_login]

        def _fake_response(*argc, **kwargs):
            return _responses.pop()

        requests = Mock()
        requests.request = _fake_response
        # check correct deployment
        with patch("cloudify_vsphere.contentlibrary.requests", requests):
            with self.assertRaises(NonRecoverableError):
                cl = contentlibrary.ContentLibrary({'host': 'host',
                                                    'username': 'username',
                                                    'password': 'password',
                                                    'allow_insecure': True})
                cl.content_item_deploy(
                    "abc", {'target': '_target'}, {'param': '_param'})


if __name__ == '__main__':
    unittest.main()
