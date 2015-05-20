########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import fabric
try:
    import json
except ImportError:
    import simplejson as json
import tempfile

import vsphere_plugin_common as vpc


def configure(vsphere_config):
    _copy_vsphere_configuration_to_manager(vsphere_config)


def _copy_vsphere_configuration_to_manager(vsphere_config):
    tmp = tempfile.mktemp()
    with open(tmp, 'w') as f:
        json.dump(vsphere_config, f)
    fabric.api.put(tmp, vpc.Config.CONNECTION_CONFIG_PATH_DEFAULT)
