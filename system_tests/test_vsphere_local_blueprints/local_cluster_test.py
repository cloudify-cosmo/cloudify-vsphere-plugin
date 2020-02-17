########
# Copyright (c) 2015-2020 Cloudify Platform Ltd. All rights reserved
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

from pyVmomi import vim

from cosmo_tester.framework.testenv import TestCase
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from . import (
    get_vsphere_entity_id_by_name,
)


class VsphereLocalClusterTest(TestCase):
    def setUp(self):
        super(VsphereLocalClusterTest, self).setUp()
        self.ext_inputs = {
            'vsphere_username': self.env.cloudify_config['vsphere_username'],
            'vsphere_password': self.env.cloudify_config['vsphere_password'],
            'vsphere_host': self.env.cloudify_config['vsphere_host'],
            'vsphere_resource_pool_name': self.env.cloudify_config[
                'vsphere_resource_pool_name'],
        }

        self.ext_inputs['vsphere_port'] = self.env.cloudify_config.get(
            'vsphere_port',
            443,
        )
        self.ext_inputs['test_cluster_name'] = self.env.cloudify_config.get(
            'test_cluster_name',
            'Cluster',
        )

        blueprints_path = os.path.split(os.path.abspath(__file__))[0]
        blueprints_path = os.path.split(blueprints_path)[0]
        self.blueprints_path = os.path.join(
            blueprints_path,
            'resources',
            'cluster'
        )

    def test_cluster_pool(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-cluster-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)

        # Do this before running the install workflow to be sure they do
        # already exist
        expected_ids = get_vsphere_entity_id_by_name(
            name=inputs['test_cluster_name'],
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
            entity_type=vim.ClusterComputeResource,
        )

        self.existing_cluster_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.existing_cluster_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.logger.info('Checking cluster ID is correct.')
        outputs = self.existing_cluster_env.outputs()
        cluster_id = outputs['vsphere_cluster_id']
        self.assertEqual(cluster_id, expected_ids)
        self.logger.info('Cluster ID is correct.')

        self.existing_cluster_env.execute('uninstall', task_retries=50)

        after_uninstall_ids = get_vsphere_entity_id_by_name(
            name=inputs['test_cluster_name'],
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
            entity_type=vim.ClusterComputeResource,
        )

        self.logger.info('Confirming cluster was not deleted on uninstall.')
        self.assertEqual(expected_ids, after_uninstall_ids)
        self.logger.info('Cluster was not deleted.')

    def test_not_existing_cluster(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'existing-cluster-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_cluster_name'] = 'systestTHISSHOULDNOTBEEXISTING'

        self.cluster_not_existing_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.cluster_not_existing_env.execute('install')
            self.cluster_not_existing_env.execute('uninstall',
                                                  task_retries=50)
            raise AssertionError(
                'Attempting to use existing cluster: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_cluster_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'not use existing' in err.message
            assert inputs['test_cluster_name'] in err.message
            assert 'no cluster by that name exists' in err.message
            self.logger.info('Use non-existing cluster with '
                             'use_external_resource has correct error.')

    def test_cluster(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'cluster-blueprint.yaml'
        )

        inputs = copy(self.ext_inputs)
        inputs['test_cluster_name'] = 'systestSHOULDNOTCREATETHIS'

        self.cluster_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        try:
            self.cluster_env.execute('install')
            self.cluster_env.execute('uninstall',
                                     task_retries=50)
            raise AssertionError(
                'Attempting to create cluster: {name} '
                'should fail, but succeeded!'.format(
                    target=inputs['test_cluster_name'],
                )
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'cannot currently be created' in err.message
            self.logger.info('Create cluster has correct error.')
