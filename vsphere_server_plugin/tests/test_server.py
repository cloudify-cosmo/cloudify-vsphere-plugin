# Copyright (c) 2018-2020 Cloudify Platform Ltd. All rights reserved
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

import json
import unittest

import vsphere_server_plugin.server as server


class ServerTest(unittest.TestCase):

    def test_validate_connect_network(self):
        examples = json.loads(json.dumps([
            ({
                'name': 'Internal',
            }, {
                'external': False,
                'from_relationship': False,
                'management': False,
                'name': 'Internal',
                'ip': None,
                'switch_distributed': False,
                'nsx_t_switch': False,
                'use_dhcp': True,
                'gateway': None,
                'network': None
            }),
            ({
                'management': True,
                'name': 'Internal',
                'ip': u'172.16.168.131',
                'switch_distributed': False,
                'nsx_t_switch': False,
                'use_dhcp': False,
                'gateway': '172.16.168.1',
                'network': u'172.16.168.0/24'
            }, {
                'external': False,
                'from_relationship': False,
                'management': True,
                'name': 'Internal',
                'ip': u'172.16.168.131',
                'switch_distributed': False,
                'nsx_t_switch': False,
                'use_dhcp': False,
                'gateway': '172.16.168.1',
                'network': '172.16.168.0/24'
            })
        ]))
        for (from_net, to_net) in examples:
            self.assertEqual(
                server.validate_connect_network(from_net), to_net
            )


if __name__ == '__main__':
    unittest.main()
