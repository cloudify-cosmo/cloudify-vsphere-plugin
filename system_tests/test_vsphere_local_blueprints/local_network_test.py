########
# Copyright (c) 2015-2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from copy import copy
import os

from cosmo_tester.framework.testenv import TestCase
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from . import (
    get_vsphere_networks,
    network_exists,
    get_vsphere_network_ids_by_name,
)


class VsphereLocalNetworkTest(TestCase):
    def setUp(self):
        super(VsphereLocalNetworkTest, self).setUp()
        self.ext_inputs = {
            'vsphere_username': self.env.cloudify_config['vsphere_username'],
            'vsphere_password': self.env.cloudify_config['vsphere_password'],
            'vsphere_host': self.env.cloudify_config['vsphere_host'],
            'vsphere_datacenter_name': self.env.cloudify_config[
                'vsphere_datacenter_name'],
            'vsphere_resource_pool_name': self.env.cloudify_config[
                'vsphere_resource_pool_name'],
        }

        if 'vsphere_port' not in self.env.cloudify_config.keys():
            self.ext_inputs['vsphere_port'] = 443

        blueprints_path = os.path.split(os.path.abspath(__file__))[0]
        blueprints_path = os.path.split(blueprints_path)[0]
        self.blueprints_path = os.path.join(
            blueprints_path,
            'resources',
            'network'
        )

    def test_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        self.logger.info('Deploying network for network test')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        if 'test_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_network_name']
        else:
            inputs['test_network_name'] = 'systestnetwork'
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

        nets = get_vsphere_networks(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        self.logger.info('Checking expected network exists')
        assert network_exists(
            name=inputs['test_network_name'],
            distributed=False,
            networks=nets,
        )
        self.logger.info('Found expected network!')

        self.logger.info('Checking network IDs are present.')
        outputs = self.network_env.outputs()
        network_ids = outputs['vsphere_network_id']
        expected_ids = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=False,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )
        self.assertEqual(network_ids, expected_ids)
        self.logger.info('Network IDs are present.')

    def test_existing_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-network-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        inputs['test_network_name'] = self.env.cloudify_config[
            'existing_standard_network']

        # Do this before running the install workflow to be sure they do
        # already exist
        expected_ids = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=False,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        self.existing_network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.existing_network_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.logger.info('Checking network IDs are correct.')
        outputs = self.existing_network_env.outputs()
        network_ids = outputs['vsphere_network_id']
        self.assertEqual(network_ids, expected_ids)
        self.logger.info('Network IDs are correct.')

        self.existing_network_env.execute('uninstall', task_retries=50)

        after_uninstall_ids = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=False,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        self.logger.info('Confirming network was not deleted on uninstall.')
        self.assertEqual(expected_ids, after_uninstall_ids)
        self.logger.info('Network was not deleted.')

    def test_not_existing_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-network-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        inputs['test_network_name'] = 'systestTHISSHOULDNOTBEEXISTING'

        self.network_not_existing_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.network_not_existing_env.execute('install')
            self.network_not_existing_env.execute('uninstall', task_retries=50)
            raise AssertionError(
                'Attempting to use existing network: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not use existing' in err.message
            assert inputs['test_network_name'] in err.message
            assert 'no network by that name exists' in err.message
            self.logger.info('Use non-existing network with '
                             'use_external_resource has correct error.')

    def test_distributed_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        self.logger.info('Deploying distributed network for network test')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        if 'test_distributed_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_distributed_network_name']
        else:
            inputs['test_network_name'] = 'systestdistributednetwork'
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

        nets = get_vsphere_networks(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        self.logger.info('Checking expected network exists')
        assert network_exists(
            name=inputs['test_network_name'],
            distributed=True,
            networks=nets,
        )
        self.logger.info('Found expected network!')

        self.logger.info('Checking network ID is present.')
        outputs = self.distributed_network_env.outputs()
        network_id = outputs['vsphere_network_id']
        expected_id = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=True,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )[0]
        self.assertEqual(network_id, expected_id)
        self.logger.info('Network ID is present.')

    def test_existing_distributed_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-network-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        inputs['test_network_name'] = self.env.cloudify_config[
            'existing_distributed_network']

        expected_id = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=True,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )[0]

        self.existing_distributed_network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.existing_distributed_network_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.logger.info('Checking network ID is correct.')
        outputs = self.existing_distributed_network_env.outputs()
        network_id = outputs['vsphere_network_id']
        self.assertEqual(expected_id, network_id)
        self.logger.info('Network ID is correct.')

        self.existing_distributed_network_env.execute('uninstall',
                                                      task_retries=50)

        after_uninstall_id = get_vsphere_network_ids_by_name(
            name=inputs['test_network_name'],
            distributed=True,
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )[0]

        self.logger.info('Confirming network was not deleted on uninstall.')
        self.assertEqual(expected_id, after_uninstall_id)
        self.logger.info('Network was not deleted.')

    def test_not_existing_distributed_network(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-network-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        inputs['test_network_name'] = 'systestTHISSHOULDNOTBEEXISTING'

        self.network_not_existing_distributed_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.network_not_existing_distributed_env.execute('install')
            self.network_not_existing_distributed_env.execute('uninstall',
                                                              task_retries=50)
            raise AssertionError(
                'Attempting to use existing distributed network: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_network_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not use existing' in err.message
            assert inputs['test_network_name'] in err.message
            assert 'no distributed network by that name exists' in err.message
            self.logger.info('Use non-existing distributed network with '
                             'use_external_resource has correct error.')

    def test_network_bad_vswitch(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = False
        inputs['test_network_name'] = 'systestTHISSHOULDNOTEXIST'
        if 'test_network_bad_vswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_bad_vswitch']
        else:
            inputs['test_network_vswitch'] = 'notarealvswitchatall'

        self.network_bad_vswitch_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.network_bad_vswitch_env.execute('install')
            self.network_bad_vswitch_env.execute('uninstall', task_retries=50)
            raise AssertionError(
                'Attempting to deploy a vswitch on invalid vswitch: {target} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_network_vswitch'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not a valid vswitch' in err.message
            assert inputs['test_network_vswitch'] in err.message
            assert 'The valid vswitches are:' in err.message
            self.logger.info('Network creation with bad vswitch has correct '
                             'error.')

    def test_network_bad_dvswitch(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-blueprint.yaml'
        )

        self.logger.info('Trying to deploy network on bad dvswitch')

        inputs = copy(self.ext_inputs)
        inputs['test_network_distributed'] = True
        inputs['test_network_name'] = 'systestTHISSHOULDNOTEXIST'
        if 'test_network_bad_dvswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_bad_dvswitch']
        else:
            inputs['test_network_vswitch'] = 'notarealdvswitchatall'

        self.network_bad_dvswitch_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.network_bad_dvswitch_env.execute('install')
            self.network_bad_dvswitch_env.execute('uninstall',
                                                  task_retries=50)
            raise AssertionError(
                'Attempting to deploy a dvswitch on invalid vswitch: '
                '{target} should fail, but succeeded!'.format(
                    target=inputs['test_network_vswitch'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not a valid dvswitch' in err.message
            assert inputs['test_network_vswitch'] in err.message
            assert 'The valid dvswitches are:' in err.message
            self.logger.info('Network creation with bad dvswitch has correct '
                             'error.')

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
