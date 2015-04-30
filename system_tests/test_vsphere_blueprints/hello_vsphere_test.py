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

import os
import urllib

from cosmo_tester.framework import testenv

from system_tests import vsphere_handler


BLUEPRINTS_DIR = os.path.join(os.path.dirname(vsphere_handler.__file__),
                              'resources')


class HelloVsphereTest(testenv.TestCase):
    """Tests vSphere with basic blueprint
       To run this tests locally you should have CLOUDIFY_AUTOMATION_TOKEN
       env variable set (see quickbuild's vars for the values)
    """
    def test_hello(self):
        self.cloudify_automation_token_ph = '{CLOUDIFY_AUTOMATION_TOKEN}'
        self.cloudify_automation_token_var = 'CLOUDIFY_AUTOMATION_TOKEN'
        blueprint_path = self.copy_blueprint(
            'hello-vsphere',
            blueprints_dir=BLUEPRINTS_DIR)
        self.blueprint_yaml = blueprint_path / 'blueprint.yaml'
        self.download_and_modify_plugin(blueprint_path)
        self.upload_deploy_and_execute_install(
            fetch_state=False,
            inputs=dict(
                template_name=self.env.template))
        vms = self.env.handler.get_vm('vsphere_test_server')
        self.assertIsNotNone(vms)
        self.execute_uninstall()

    def download_and_modify_plugin(self, blueprint_path):
        plugins_branch = self.env.plugins_branch
        url = 'http://getcloudify.org.s3.amazonaws.com' \
              '/spec/vsphere-plugin/' + plugins_branch + '/plugin.yaml'
        plugin = urllib.URLopener()
        file_path = blueprint_path + "/plugin.yaml"
        plugin.retrieve(url, file_path)
        with open(file_path, 'r') as f:
            newlines = []
            for line in f.readlines():
                newlines.append(line.replace
                                (self.cloudify_automation_token_ph,
                                    os.environ.get
                                    (self.cloudify_automation_token_var)))
        with open(file_path, 'w') as f:
            for line in newlines:
                f.write(line)
