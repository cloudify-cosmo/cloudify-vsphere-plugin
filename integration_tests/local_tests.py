# #######
# Copyright (c) 2018 Cloudify Platform Ltd. All rights reserved
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

from copy import deepcopy
from os import getenv, path
from time import sleep
import unittest

from fabric.api import settings as fabric_settings, run as fabric_run
from cloudify.workflows import local


IGNORED_LOCAL_WORKFLOW_MODULES = (
    'worker_installer.tasks',
    'plugin_installer.tasks',
    'cloudify_agent.operations',
    'cloudify_agent.installer.operations',
)

RETRY_MAX = 10
RETRY_INT = 1


class TestEnvironmentValidationError(Exception):
    pass


class LiveUseCaseTests(unittest.TestCase):

    def setUp(self):
        super(LiveUseCaseTests, self).setUp()

    @property
    def client_config(self):
        return {
            'host': getenv('vsphere_host'),
            'port': getenv('vsphere_port'),
            'datacenter_name': getenv('vsphere_datacenter_name'),
            'resource_pool_name': getenv('vsphere_resource_pool_name'),
            'allow_insecure': getenv('vsphere_allow_insecure'),
            'auto_placement': getenv('vsphere_auto_placement'),
            'username': getenv('vsphere_username'),
            'password': getenv('vsphere_password'),
        }

    def initialize_local_blueprint(self, test_name=None, inputs=None):
        cfy_local = local.init_env(
            self.blueprint_path,
            test_name or self.test_name,
            inputs=inputs or self.inputs,
            ignored_modules=IGNORED_LOCAL_WORKFLOW_MODULES)
        if test_name:
            return cfy_local
        self.cfy_local = cfy_local

    def install_blueprint(self,
                          task_retries=RETRY_MAX,
                          task_retry_interval=RETRY_INT,
                          cfy_local=None):

        if cfy_local:
            cfy_local.execute(
                'install',
                task_retries=task_retries,
                task_retry_interval=task_retry_interval)
        else:
            self.cfy_local.execute(
                'install',
                task_retries=task_retries,
                task_retry_interval=task_retry_interval)

    def uninstall_blueprint(self,
                            task_retries=RETRY_MAX,
                            task_retry_interval=RETRY_INT,
                            ignore_failure=False,
                            cfy_local=None):

        if ignore_failure:
            self.cfy_local.execute(
                'uninstall',
                parameters={'ignore_failure': True},
                task_retries=task_retries,
                task_retry_interval=task_retry_interval)
        elif cfy_local:
            cfy_local.execute(
                'uninstall',
                parameters={'ignore_failure': True},
                task_retries=task_retries,
                task_retry_interval=task_retry_interval)
        else:
            self.cfy_local.execute(
                'uninstall',
                task_retries=task_retries,
                task_retry_interval=task_retry_interval)

    def cleanup_uninstall(self):
        self.uninstall_blueprint(ignore_failure=True)

    def cleanup_command(self, cleaup_command, **kwargs):
        cleaup_command(kwargs)

    def test_network(self, *_):
        self.test_name = 'test_network'
        self.blueprint_path = './examples/network.yaml'
        self.inputs = dict(self.client_config)
        self.initialize_local_blueprint()
        self.addCleanup(self.cleanup_uninstall)
        self.install_blueprint()
        self.uninstall_blueprint()

    def test_compute(self, *_):
        self.test_name = 'test_compute'
        self.blueprint_path = './examples/compute.yaml'
        self.inputs = dict(self.client_config)
        self.initialize_local_blueprint()
        self.addCleanup(self.cleanup_uninstall)
        self.install_blueprint()
        sleep(10)
        try:
            server_node_instance = \
                self.cfy_local.storage.get_node_instances('vm')[0]
            ip_address = \
                server_node_instance.runtime_properties['public_ip']
        except (KeyError, IndexError) as e:
            raise Exception('Missing Runtime Property: {0}'.format(str(e)))

        with fabric_settings(
                host_string=ip_address,
                key_filename=path.join(path.expanduser('~/'),
                                       '.ssh/vmware-centos.key'),
                user='centos',
                abort_on_prompts=True):
            fabric_run_output = fabric_run('last')
            self.assertEqual(0, fabric_run_output.return_code)
        self.uninstall_blueprint()

    def test_compute_network(self, *_):
        self.test_name = 'test_compute_network'
        self.blueprint_path = './examples/compute-network.yaml'
        self.inputs = dict(self.client_config)
        self.initialize_local_blueprint()
        self.addCleanup(self.cleanup_uninstall)
        self.install_blueprint()
        sleep(10)
        try:
            server_node_instance = \
                self.cfy_local.storage.get_node_instances('vm')[0]
            ip_address = \
                server_node_instance.runtime_properties['ip']
        except (KeyError, IndexError) as e:
            raise Exception('Missing Runtime Property: {0}'.format(str(e)))

        with fabric_settings(
                host_string=ip_address,
                key_filename=path.join(path.expanduser('~/'),
                                       '.ssh/vmware-centos.key'),
                user='centos',
                abort_on_prompts=True):
            fabric_run_output = fabric_run('last')
            self.assertEqual(0, fabric_run_output.return_code)
        self.uninstall_blueprint()

    def test_compute_storage(self, *_):
        self.test_name = 'test_network'
        self.blueprint_path = './examples/compute-storage.yaml'
        self.inputs = dict(self.client_config)
        self.initialize_local_blueprint()
        self.addCleanup(self.cleanup_uninstall)
        self.install_blueprint()
        self.uninstall_blueprint()

    def test_existing_compute_storage(self, *_):
        # Install the Actual VM
        self.test_name = 'test_existing_compute'
        self.blueprint_path = './examples/compute-storage.yaml'
        self.inputs = dict(self.client_config)
        self.initialize_local_blueprint()
        self.addCleanup(self.cleanup_uninstall)
        self.install_blueprint()
        sleep(10)
        try:
            server_node_instance = \
                self.cfy_local.storage.get_node_instances('vm')[0]
            server_name = \
                server_node_instance.runtime_properties['name']
        except (KeyError, IndexError) as e:
            raise Exception('Missing Runtime Property: {0}'.format(str(e)))

        # "Install" the "External" VM
        new_inputs = deepcopy(self.inputs)
        new_inputs.update({'old_vm': True, 'server_name': server_name})
        _cfy_local = self.initialize_local_blueprint(self.test_name + '2', new_inputs)
        self.install_blueprint(cfy_local=_cfy_local)
        try:
            server_node_instance = \
                _cfy_local.storage.get_node_instances('vm')[0]
            ip_address = \
                server_node_instance.runtime_properties['public_ip']
        except (KeyError, IndexError) as e:
            raise Exception('Missing Runtime Property: {0}'.format(str(e)))

        with fabric_settings(
                host_string=ip_address,
                key_filename=path.join(path.expanduser('~/'),
                                       '.ssh/vmware-centos.key'),
                user='centos',
                abort_on_prompts=True):
            fabric_run_output = fabric_run('last')
            self.assertEqual(0, fabric_run_output.return_code)
        self.uninstall_blueprint()
