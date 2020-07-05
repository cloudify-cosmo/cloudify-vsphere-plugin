#########
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

import os
import unittest

from mock import MagicMock, patch
from pyfakefs import fake_filesystem_unittest

from cloudify.state import current_ctx

from ..clients import Config


class VspherePluginCommonFSTests(fake_filesystem_unittest.TestCase):

    def setUp(self):
        super(VspherePluginCommonFSTests, self).setUp()
        self.setUpPyfakefs()
        self.mock_ctx = MagicMock()
        current_ctx.set(self.mock_ctx)

    @patch('vsphere_plugin_common.utils.ctx')
    def _simple_deprecated_test(self, path, mock_ctx):
        evaled_path = os.getenv(path, path)
        expanded_path = os.path.expanduser(evaled_path)
        self.fs.create_file(expanded_path)

        config = Config()
        ret = config._find_config_file()

        self.assertEqual(expanded_path, ret)

        mock_ctx.logger.warn.assert_called_with(
            'Deprecated configuration options were found: {}'.format(path)
        )

    def test_choose_root(self):
        self._simple_deprecated_test('/root/connection_config.yaml')

    def test_choose_home(self):
        self._simple_deprecated_test('~/connection_config.yaml')

    def test_choose_old_envvar(self):
        with patch.dict('os.environ', {'CONNECTION_CONFIG_PATH': '/a/path'}):
            self._simple_deprecated_test('CONNECTION_CONFIG_PATH')

    def test_choose_config_file(self):
        self.fs.create_file(
            '/etc/cloudify/vsphere_plugin/connection_config.yaml')
        self.addCleanup(
            self.fs.RemoveFile,
            '/etc/cloudify/vsphere_plugin/connection_config.yaml')

        config = Config()
        ret = config._find_config_file()

        self.assertEqual(
            ret,
            '/etc/cloudify/vsphere_plugin/connection_config.yaml')

    def test_no_file(self):
        config = Config()

        ret = config.get()

        self.mock_ctx.logger.warn.assert_called_once_with(
            'Unable to read configuration file '
            '/etc/cloudify/vsphere_plugin/connection_config.yaml.'
        )
        self.assertEqual(ret, {})

    def test_new_envvar(self):
        self.fs.create_file(
            '/a/pth',
            contents="{'some': 'contents'}\n"
        )
        with patch.dict('os.environ', {'CFY_VSPHERE_CONFIG_PATH': '/a/pth'}):
            config = Config()

            ret = config.get()

        self.assertEqual({'some': 'contents'}, ret)


if __name__ == '__main__':
    unittest.main()
