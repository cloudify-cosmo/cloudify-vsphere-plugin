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

from copy import copy
import os

from cosmo_tester.framework.testenv import TestCase
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from . import (
    get_vsphere_vms_list,
    check_correct_vm_name,
    get_runtime_props,
    check_vm_name_in_runtime_properties,
)


class VsphereLocalLinuxTest(TestCase):
    def setUp(self):
        super(VsphereLocalLinuxTest, self).setUp()
        self.ext_inputs = {
            'template_name': self.env.cloudify_config['linux_template'],
            'external_network': self.env.cloudify_config[
                'external_network_name'],
            'management_network': self.env.cloudify_config[
                'management_network_name'],
            'vsphere_username': self.env.cloudify_config['vsphere_username'],
            'vsphere_password': self.env.cloudify_config['vsphere_password'],
            'vsphere_host': self.env.cloudify_config['vsphere_host'],
            'vsphere_datacenter_name': self.env.cloudify_config[
                'vsphere_datacenter_name'],
            'vsphere_resource_pool_name': self.env.cloudify_config[
                'vsphere_resource_pool_name'],
            'vsphere_auto_placement': self.env.cloudify_config[
                'vsphere_auto_placement'],
        }

        if 'vsphere_port' not in self.env.cloudify_config.keys():
            self.ext_inputs['vsphere_port'] = 443

        for optional_key in [
            'external_network_distributed',
            'management_network_distributed',
        ]:
            if optional_key in self.env.cloudify_config.keys():
                self.ext_inputs[optional_key] = \
                    self.env.cloudify_config[optional_key]

        blueprints_path = os.path.split(os.path.abspath(__file__))[0]
        blueprints_path = os.path.split(blueprints_path)[0]
        self.blueprints_path = os.path.join(
            blueprints_path,
            'resources',
            'linux'
        )

    def test_naming(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'naming-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying linux host with name assigned')

        self.naming_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.naming_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_naming)

        self.logger.info('Searching for appropriately named VM')
        vms = get_vsphere_vms_list(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=self.naming_env.storage.get_node_instances(),
            logger=self.logger,
        )

        name_prefix = 'systemtestlinuxnaming'
        check_correct_vm_name(
            vms=vms,
            name_prefix=name_prefix,
            logger=self.logger,
        )
        check_vm_name_in_runtime_properties(
            runtime_props=runtime_properties,
            name_prefix=name_prefix,
            logger=self.logger,
        )

    def test_naming_no_name(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'naming_no_name-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying linux host without name assigned')

        self.naming_no_name_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.naming_no_name_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_naming_no_name)

        self.logger.info('Searching for appropriately named VM')
        vms = get_vsphere_vms_list(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        instances = self.naming_no_name_env.storage.get_node_instances()
        name_prefix = 'systemtestlinuxnamingnoname'
        runtime_properties = get_runtime_props(
            target_node_id=name_prefix,
            node_instances=instances,
            logger=self.logger,
        )

        check_correct_vm_name(
            vms=vms,
            name_prefix=name_prefix,
            logger=self.logger,
        )
        check_vm_name_in_runtime_properties(
            runtime_props=runtime_properties,
            name_prefix=name_prefix,
            logger=self.logger,
        )

    def test_storage(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'storage-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying linux host for storage test')

        inputs = copy(self.ext_inputs)
        if 'ssh_user' in self.env.cloudify_config.keys():
            inputs['username'] = self.env.cloudify_config['ssh_user']
        if 'ssh_key_filename' in self.env.cloudify_config.keys():
            inputs['key_path'] = self.env.cloudify_config['ssh_key_filename']

        self.storage_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.storage_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_storage)

        scsi_id = self.storage_env.outputs()['scsi_id']
        scsi_id = scsi_id.split(':')
        assert len(scsi_id) == 2

        # Assert that the bus ID is valid
        assert 0 <= int(scsi_id[0])

        # Assert that this is a valid SCSI unit ID
        assert 0 < int(scsi_id[1]) < 16
        # 7 is expected to be the controller unit number
        assert int(scsi_id[1]) != 7

    def test_double_storage(self):
        # Based on an issue reported where trying to have two disks attached
        # to one VM results in failures
        blueprint = os.path.join(
            self.blueprints_path,
            'double_storage-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying linux host for double storage test')

        inputs = copy(self.ext_inputs)
        if 'ssh_user' in self.env.cloudify_config.keys():
            inputs['username'] = self.env.cloudify_config['ssh_user']
        if 'ssh_key_filename' in self.env.cloudify_config.keys():
            inputs['key_path'] = self.env.cloudify_config['ssh_key_filename']

        self.double_storage_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.double_storage_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_double_storage)

        scsi_ids = self.double_storage_env.outputs()['scsi_ids']
        for scsi_id in scsi_ids:
            scsi_id = scsi_id.split(':')
            assert len(scsi_id) == 2

            # Assert that the bus ID is valid
            assert 0 <= int(scsi_id[0])

            # Assert that this is a valid SCSI unit ID
            assert 0 < int(scsi_id[1]) < 16
            # 7 is expected to be the controller unit number
            assert int(scsi_id[1]) != 7

    def test_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying network and linux hosts for network test')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        if 'ssh_user' in self.env.cloudify_config.keys():
            inputs['username'] = self.env.cloudify_config['ssh_user']
        if 'ssh_key_filename' in self.env.cloudify_config.keys():
            inputs['key_path'] = self.env.cloudify_config['ssh_key_filename']
        if 'test_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_network_name']
        if 'test_network_vlan' in self.env.cloudify_config.keys():
            inputs['test_network_vlan'] = self.env.cloudify_config[
                'test_network_vlan']
        if 'test_network_vswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_vswitch']

        self.network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.network_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_network)

        test_results = self.network_env.outputs()['test_results']
        assert True in test_results

    def test_distributed_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying network and linux hosts for distributed '
                         'network test')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        if 'ssh_user' in self.env.cloudify_config.keys():
            inputs['username'] = self.env.cloudify_config['ssh_user']
        if 'ssh_key_filename' in self.env.cloudify_config.keys():
            inputs['key_path'] = self.env.cloudify_config['ssh_key_filename']
        if 'test_distributed_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_distributed_network_name']
        if 'test_network_vlan' in self.env.cloudify_config.keys():
            inputs['test_network_vlan'] = self.env.cloudify_config[
                'test_network_vlan']
        if 'test_network_dvswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_dvswitch']

        self.distributed_network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.distributed_network_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_distributed_network)

        test_results = self.distributed_network_env.outputs()['test_results']
        assert True in test_results

    def cleanup_network(self):
        self.network_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_distributed_network(self):
        self.distributed_network_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_storage(self):
        self.storage_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_double_storage(self):
        self.double_storage_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_naming(self):
        self.naming_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_naming_no_name(self):
        self.naming_no_name_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )
