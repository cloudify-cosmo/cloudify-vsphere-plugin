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

# Stdlib imports
import os
from copy import copy

# Third party imports

# Cloudify imports
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from cosmo_tester.framework.testenv import TestCase

# This package imports
from . import (
    get_runtime_props,
    get_vsphere_vms_list,
    check_correct_vm_name,
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

        self.addCleanup(
            self.generic_cleanup,
            self.naming_env,
        )

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

    def test_naming_underscore_to_hyphen(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'naming_underscore-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.naming_underscore_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.naming_underscore_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(
            self.generic_cleanup,
            self.naming_underscore_env,
        )

        self.logger.info('Searching for appropriately named VM')
        vms = get_vsphere_vms_list(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=(
                self.naming_underscore_env.storage.get_node_instances()
            ),
            logger=self.logger,
        )

        name_prefix = 'systemtest-linuxnaming'
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

        self.addCleanup(
            self.generic_cleanup,
            self.naming_no_name_env,
        )

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

    def test_no_external_net(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'no-external-net-blueprint.yaml'
        )

        self.logger.info(
            'Deploying linux host with no external network assigned'
        )

        self.no_external_net_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.no_external_net_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(
            self.generic_cleanup,
            self.no_external_net_env,
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=(
                self.no_external_net_env.storage.get_node_instances()
            ),
            logger=self.logger,
        )

        assert runtime_properties['ip'] is not None
        assert runtime_properties['public_ip'] is None

    def test_no_management_net(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'no-management-net-blueprint.yaml'
        )

        self.logger.info(
            'Deploying linux host with no management network assigned'
        )

        self.no_management_net_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.no_management_net_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(
            self.generic_cleanup,
            self.no_management_net_env,
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=(
                self.no_management_net_env.storage.get_node_instances()
            ),
            logger=self.logger,
        )

        assert runtime_properties['public_ip'] is not None
        assert runtime_properties['ip'] == runtime_properties['public_ip']

    def test_no_interfaces(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'no-interfaces-blueprint.yaml'
        )

        self.logger.info(
            'Deploying linux host with no interfaces attached'
        )

        self.no_interfaces_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.no_interfaces_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=(
                self.no_interfaces_env.storage.get_node_instances()
            ),
            logger=self.logger,
        )

        self.addCleanup(
            self.generic_cleanup,
            self.no_interfaces_env,
        )

        assert runtime_properties['public_ip'] is None
        assert runtime_properties['ip'] is None

    def test_storage(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'storage-blueprint.yaml'
        )

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

        self.addCleanup(
            self.generic_cleanup,
            self.storage_env,
        )

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

        self.addCleanup(
            self.generic_cleanup,
            self.double_storage_env,
        )

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

        self.addCleanup(
            self.generic_cleanup,
            self.network_env,
        )

        test_results = self.network_env.outputs()['test_results']
        assert True in test_results

    def test_distributed_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

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

        self.addCleanup(
            self.generic_cleanup,
            self.distributed_network_env,
        )

        test_results = self.distributed_network_env.outputs()['test_results']
        assert True in test_results

    def test_invalid_network_name(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-fail-blueprint.yaml'
        )

        self.logger.info('Attempting to deploy with invalid network name')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        inputs['test_network_name'] = 'notarealnetworkdonotuse'
        inputs.pop('external_network_distributed')

        self.invalid_network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.invalid_network_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.invalid_network_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with an invalid network was expected to fail, but '
                'succeeded. Network name was {}'.format(
                    inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert inputs['test_network_name'] in err.message
            assert 'not present' in err.message
            assert 'Available networks are:' in err.message

    def test_incorrect_switch_distributed_true(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-fail-blueprint.yaml'
        )

        self.logger.info(
            'Attempting to deploy on standard network with '
            'switch_distributed set to true'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        inputs['test_network_name'] = (
            self.env.cloudify_config['existing_standard_network']
        )
        inputs.pop('external_network_distributed')

        self.incorrect_distributed_true_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.incorrect_distributed_true_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.incorrect_distributed_true_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with an invalid distributed network was expected '
                'to fail, but succeeded. Network name was {}'.format(
                    inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert inputs['test_network_name'] in err.message
            assert 'not present' in err.message
            assert (
                'You may need to set the switch_distributed setting for this '
                'network to false'
            ) in err.message

    def test_invalid_distributed_network_name(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-fail-blueprint.yaml'
        )

        self.logger.info(
            'Attempting to deploy with invalid distributed network name'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        inputs['test_network_name'] = 'notarealdistributednetworkdonotuse'
        inputs.pop('external_network_distributed')

        self.invalid_distributed_network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.invalid_distributed_network_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.invalid_distributed_network_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with an invalid distributed network was expected '
                'to fail, but succeeded. Network name was {}'.format(
                    inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert inputs['test_network_name'] in err.message
            assert 'not present' in err.message
            assert 'Available distributed networks are:' in err.message

    def test_incorrect_switch_distributed_false(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-fail-blueprint.yaml'
        )

        self.logger.info(
            'Attempting to deploy on distributed network with '
            'switch_distributed set to false'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        inputs['test_network_name'] = (
            self.env.cloudify_config['existing_distributed_network']
        )
        inputs.pop('external_network_distributed')

        self.incorrect_distributed_false_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.incorrect_distributed_false_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.incorrect_distributed_false_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with an invalid standard network was expected '
                'to fail, but succeeded. Network name was {}'.format(
                    inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert inputs['test_network_name'] in err.message
            assert 'not present' in err.message
            assert (
                'You may need to set the switch_distributed setting for this '
                'network to true'
            ) in err.message

    def test_network_from_relationship_missing_target(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-relationship-fail-no-target-blueprint.yaml',
        )

        self.logger.info(
            'Attempting to deploy VM with network from missing relationship.'
        )

        inputs = copy(self.ext_inputs)
        inputs['external_network'] = 'not_a_real_node'
        inputs.pop('external_network_distributed')

        self.network_from_missing_relationship_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES,
        )

        try:
            self.network_from_missing_relationship_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.network_from_missing_relationship_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with a network from a missing relationship was '
                'expected to fail, but succeeded. Network name was {}'.format(
                    inputs['external_network'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'Could not find' in err.message
            assert 'relationship' in err.message
            assert 'called' in err.message
            assert inputs['external_network'] in err.message

    def test_network_from_relationship_bad_target(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-relationship-fail-bad-target-blueprint.yaml',
        )

        self.logger.info(
            'Attempting to deploy VM with network from relationship to '
            'target without required attributes.'
        )

        inputs = copy(self.ext_inputs)
        # The connection_configuration node will exist but not have the
        # runtime properties
        inputs['external_network'] = 'connection_configuration'

        self.network_from_bad_relationship_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES,
        )

        try:
            self.network_from_bad_relationship_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.network_from_bad_relationship_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with a network from a bad relationship was '
                'expected to fail, but succeeded. Network name was {}'.format(
                    inputs['external_network'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'Could not get' in err.message
            assert 'vsphere_network_id' in err.message
            assert 'from relationship' in err.message
            assert inputs['external_network'] in err.message

    def test_incorrect_inputs(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'fail-blueprint.yaml'
        )

        self.logger.info('Attempting to deploy with bad inputs.')

        bad_allowed_hosts = ['not a real host', 'really not a real host']
        bad_allowed_clusters = ['not a real cluster',
                                'really not a real cluster']
        bad_allowed_datastores = ['not a real datastore',
                                  'really not a real datastore']
        expected_bad_datacenter = 'this is not a real datacenter'
        expected_bad_resource_pool = 'this is not a real resource pool'
        expected_bad_template = 'this is not a real template'

        inputs = copy(self.ext_inputs)
        inputs['cpus'] = 0
        inputs['memory'] = 0
        inputs['allowed_hosts'] = bad_allowed_hosts
        inputs['allowed_clusters'] = bad_allowed_clusters
        inputs['allowed_datastores'] = bad_allowed_datastores
        inputs['vsphere_datacenter_name'] = expected_bad_datacenter
        inputs['vsphere_resource_pool_name'] = expected_bad_resource_pool
        inputs['template_name'] = expected_bad_template

        for undesirable_input in [
            'external_network_distributed',
            'management_network_distributed',
        ]:
            try:
                inputs.pop(undesirable_input)
            except KeyError:
                # Optional input not present, ignore
                pass

        self.incorrect_inputs_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.incorrect_inputs_env.execute(
                'install',
                task_retries=50,
                task_retry_interval=3,
            )
            self.incorrect_inputs_env.execute(
                'uninstall',
                task_retries=50,
                task_retry_interval=3,
            )
            raise AssertionError(
                'Deploying with invalid inputs was expected '
                'to fail, but succeeded.'
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            for information in [
                'No allowed hosts exist',
                'No allowed clusters exist',
                'No allowed datastores exist',
                'Existing host(s):',
                'Existing cluster(s):',
                'Existing datastore(s):',
                'VM template {name} could not be found'.format(
                    name=expected_bad_template,
                ),
                'Resource pool {name} could not be found'.format(
                    name=expected_bad_resource_pool,
                ),
                'Datacenter {name} could not be found'.format(
                    name=expected_bad_datacenter,
                ),
                'At least one vCPU',
                'memory cannot be less than 1MB',
            ]:
                assert information in err.message

    def generic_cleanup(self, component):
        component.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )
