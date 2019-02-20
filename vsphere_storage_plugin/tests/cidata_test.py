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

from mock import MagicMock

from cloudify.state import current_ctx

from vsphere_storage_plugin import cidata


class VsphereCIDataTest(unittest.TestCase):

    def setUp(self):
        super(VsphereCIDataTest, self).setUp()
        self.mock_ctx = MagicMock()
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


if __name__ == '__main__':
    unittest.main()
