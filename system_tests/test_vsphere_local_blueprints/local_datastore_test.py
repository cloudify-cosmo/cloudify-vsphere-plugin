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

from pyVmomi import vim

from cosmo_tester.framework.testenv import TestCase
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from . import (
    get_vsphere_entity_id_by_name,
)


class VsphereLocalDatastoreTest(TestCase):
    def setUp(self):
        super(VsphereLocalDatastoreTest, self).setUp()
        self.ext_inputs = {
            'vsphere_username': self.env.cloudify_config['vsphere_username'],
            'vsphere_password': self.env.cloudify_config['vsphere_password'],
            'vsphere_host': self.env.cloudify_config['vsphere_host'],
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
            'datastore'
        )

    def test_existing_datastore(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-datastore-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_datastore_name'] = self.env.cloudify_config[
            'vsphere_datastore_name']

        # Do this before running the install workflow to be sure they do
        # already exist
        expected_ids = get_vsphere_entity_id_by_name(
            name=inputs['test_datastore_name'],
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
            entity_type=vim.Datastore,
        )

        self.existing_datastore_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.existing_datastore_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.logger.info('Checking datastore ID is correct.')
        outputs = self.existing_datastore_env.outputs()
        datastore_id = outputs['vsphere_datastore_id']
        self.assertEqual(datastore_id, expected_ids)
        self.logger.info('Datastore ID is correct.')

        self.existing_datastore_env.execute('uninstall', task_retries=50)

        after_uninstall_ids = get_vsphere_entity_id_by_name(
            name=inputs['test_datastore_name'],
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
            entity_type=vim.Datastore,
        )

        self.logger.info('Confirming datastore was not deleted on uninstall.')
        self.assertEqual(expected_ids, after_uninstall_ids)
        self.logger.info('Datastore was not deleted.')

    def test_not_existing_datastore(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-datastore-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_datastore_name'] = 'systestTHISSHOULDNOTBEEXISTING'

        self.datastore_not_existing_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.datastore_not_existing_env.execute('install')
            self.datastore_not_existing_env.execute('uninstall',
                                                    task_retries=50)
            raise AssertionError(
                'Attempting to use existing datastore: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_datastore_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not use existing' in err.message
            assert inputs['test_datastore_name'] in err.message
            assert 'no datastore by that name exists' in err.message
            self.logger.info('Use non-existing datastore with '
                             'use_external_resource has correct error.')

    def test_datastore(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'datastore-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_datastore_name'] = 'systestSHOULDNOTCREATETHIS'

        self.datastore_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.datastore_env.execute('install')
            self.datastore_env.execute('uninstall',
                                       task_retries=50)
            raise AssertionError(
                'Attempting to create datastore: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_datastore_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'cannot currently be created' in err.message
            self.logger.info('Create datastore has correct error.')
