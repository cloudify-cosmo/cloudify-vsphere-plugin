########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
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

from cosmo_tester.test_suites.test_blueprints import nodecellar_test


class VsphereNodeCellarTest(nodecellar_test.NodecellarAppTest):

    def test_vsphere_nodecellar(self):
        self._test_nodecellar_impl('vsphere-nodecellar.yaml')

    def get_inputs(self):

        return {
            'template_name': self.env.template,
            'agent_user': 'giga',
            'management_network': 'Management',
            'external_network': 'DMZ',
        }

    @property
    def expected_nodes_count(self):
        return 5

    @property
    def entrypoint_node_name(self):
        return 'nodejs_host'

    @property
    def entrypoint_property_name(self):
        return 'public_ip'
