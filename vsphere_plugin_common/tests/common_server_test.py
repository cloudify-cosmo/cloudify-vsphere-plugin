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
import unittest

from mock import Mock, MagicMock, patch

import vsphere_plugin_common


class PluginCommonUnitTests(unittest.TestCase):

    @patch('vsphere_plugin_common.get_ip_from_vsphere_nic_ips')
    def test_get_server_ip(self, get_ip_from_nic_mock):
        client = vsphere_plugin_common.ServerClient()
        server = Mock()
        server.guest.net = [
            MagicMock(name='oobly'),
            MagicMock(name='hoobly'),
        ]
        server.guest.net[0].network = 'oobly'
        server.guest.net[0].ipAddress = '10.11.12.13'
        server.guest.net[1].network = 'hoobly'
        server.guest.net[1].ipAddress = '10.11.12.14'

        res = client.get_server_ip(server, 'hoobly')

        self.assertEqual(
            get_ip_from_nic_mock.return_value,
            res)

    @patch('vsphere_plugin_common.get_ip_from_vsphere_nic_ips')
    def test_get_server_ip_with_slash(self, get_ip_from_nic_mock):
        client = vsphere_plugin_common.ServerClient()
        server = Mock()
        server.guest.net = [
            MagicMock(name='oobly/hoobly'),
        ]
        server.guest.net[0].network = 'oobly%2fhoobly'
        server.guest.net[0].ipAddress = '10.11.12.13'

        res = client.get_server_ip(server, 'oobly/hoobly')

        self.assertEqual(
            get_ip_from_nic_mock.return_value,
            res)


if __name__ == '__main__':
    unittest.main()
