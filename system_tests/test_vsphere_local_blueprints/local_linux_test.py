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

# Stdlib imports
import os
import re
import sys
import urllib
import threading
from bdb import Bdb
from contextlib import contextmanager
from copy import copy
from functools import partial

# Third party imports
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect

# Cloudify imports
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from cosmo_tester.framework.testenv import TestCase

# This package imports
import vsphere_plugin_common
from . import (
    PlatformCaller,
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
        else:
            self.ext_inputs['vsphere_port'] = (
                self.env.cloudify_config['vsphere_port']
            )

        if 'certificate_path' in self.env.cloudify_config.keys():
            self.ext_inputs['certificate_path'] = (
                self.env.cloudify_config['certificate_path']
            )
            self.ext_inputs['allow_insecure'] = False
        else:
            self.ext_inputs['allow_insecure'] = True

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

        inputs = copy(self.ext_inputs)
        inputs.pop('vsphere_auto_placement')

        self.logger.info('Deploying linux host with name assigned')

        self.naming_env = local.init_env(
            blueprint,
            inputs=inputs,
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
        # This test abuses bdb to hack around with the storage.create operation
        # in the middle of a function. That means debugging using pdb, ipdb or
        # similar which make use of sys.settrace will break this test.
        # IPython.embed can be safely used instead.
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
        self.addCleanup(
            self.generic_cleanup,
            self.double_storage_env,
        )

        class Edb(Bdb):
            """
            This "debugger" class will actually sabotage a call to
            StorageClient.create_storage by inspecting the config_spec it
            produces and then creating the disk it's about to create.

            Once it has performed the sabotage it deactivates itself by calling
            sys.settrace(None).
            """

            def __init__(self, *args, **kwargs):
                Bdb.__init__(self, *args, **kwargs)
                self.ran_continue = False
                self.sabotage_complete = False

            def user_call(self, frame, args):
                if not self.ran_continue:
                    print('first')
                    self.set_continue()
                    self.ran_continue = True

            def user_line(self, frame):
                if self.sabotage_complete:
                    # Stop running this tracer
                    sys.settrace(None)
                    return
                self.set_next(frame)

                if 'config_spec' in frame.f_locals:
                    print('found it')
                    spec = frame.f_locals['config_spec']
                    spec.deviceChange = frame.f_locals['devices']
                    task = frame.f_locals['vm'].obj.Reconfigure(spec=spec)
                    frame.f_locals['self']._wait_for_task(task)
                    self.sabotage_complete = True

        bug = Edb()

        filename = vsphere_plugin_common.__file__
        if filename.endswith('pyc'):
            filename = filename[:-1]
        with open(filename) as f:
            for lineno, line in enumerate(f, 1):
                if re.match('    def create_storage', line):
                    print('file: "{}" line: {}'.format(filename, lineno))
                    break
            else:
                self.fail('function not found')

        bug.reset()
        bug.set_break(filename, lineno + 1)

        old_tracer = threading._trace_hook
        threading.settrace(bug.trace_dispatch)

        self.double_storage_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        threading.settrace(old_tracer)

        if not bug.sabotage_complete:
            self.fail("Sabotage of storage creation didn't work")

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

    def test_network(self, net_name=None):
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
        if 'test_network_vlan' in self.env.cloudify_config.keys():
            inputs['test_network_vlan'] = self.env.cloudify_config[
                'test_network_vlan']
        if 'test_network_vswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_vswitch']

        if net_name:
            inputs['test_network_name'] = net_name
        elif 'test_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_network_name']

        self.network_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.network_env,
        )

        self.network_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        test_results = self.network_env.outputs()['test_results']
        assert True in test_results

    def test_network_with_slash(self):
        if 'test_network_name' in self.env.cloudify_config.keys():
            net_name = self.env.cloudify_config['test_network_name']
        else:
            net_name = 'test_network_name'
        net_name = net_name[0] + '/' + net_name[1:]
        return self.test_network(net_name)

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

    def test_resize(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.resize_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.resize_env,
        )

        self.resize_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.logger.info('Searching for appropriately named VM')
        vms = get_vsphere_vms_list(
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )

        self.resize_env.execute(
            'execute_operation',
            parameters={
                'node_ids': 'testserver',
                'operation': 'cloudify.interfaces.modify.resize',
                'operation_kwargs': {
                    'cpus': 2,
                    'memory': 3072,
                },
            },
            task_retries=10,
            task_retry_interval=3,
        )

        runtime_properties = get_runtime_props(
            target_node_id='testserver',
            node_instances=self.resize_env.storage.get_node_instances(),
            logger=self.logger,
        )

        vsphere_conn = SmartConnect(
            user=self.ext_inputs['vsphere_username'],
            pwd=self.ext_inputs['vsphere_password'],
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
        )
        vsphere_content = vsphere_conn.RetrieveContent()
        vsphere_container = vsphere_content.viewManager.CreateContainerView(
            vsphere_content.rootFolder,
            [vim.VirtualMachine],
            True,
        )
        vms = vsphere_container.view
        vsphere_container.Destroy()
        config = None
        for vm in vms:
            if vm.name == runtime_properties['name']:
                config = vm.summary.config

        for vim_key, attrs_key, value in (
            ('numCpu', 'cpus', 2),
            ('memorySizeMB', 'memory', 3072),
        ):
            self.assertEqual(value, getattr(config, vim_key))
            self.assertEqual(value, runtime_properties[attrs_key])

        Disconnect(vsphere_conn)

    def test_resize_too_big(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.resize_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.resize_env,
        )

        self.resize_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        with self.assertRaises(RuntimeError) as e:
            self.resize_env.execute(
                'execute_operation',
                parameters={
                    'node_ids': 'testserver',
                    'operation': 'cloudify.interfaces.modify.resize',
                    'operation_kwargs': {
                        'cpus': 2,
                        'memory': 4096,
                    },
                },
                task_retries=10,
                task_retry_interval=3,
            )

        self.assertIn('https://kb.vmware.com/kb/2008405', str(e.exception))

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

    def test_power_on_off(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.power_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.power_env,
        )

        self.power_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        def exec_op(operation):
            return self.power_env.execute(
                'execute_operation',
                parameters={
                    'node_ids': 'testserver',
                    'operation': operation,
                },
                task_retries=10,
                task_retry_interval=3,
            )

        vm = partial(
            self.get_vim_object,
            vim.VirtualMachine,
            self.power_env.storage.get_node_instances('testserver')
            [0].runtime_properties['name'],
        )

        exec_op('cloudify.interfaces.power.off')

        self.assertEqual('poweredOff', vm().summary.runtime.powerState)

        # powering on off twice in a row should not change state.
        exec_op('cloudify.interfaces.power.off')

        self.assertEqual('poweredOff', vm().summary.runtime.powerState)

        exec_op('cloudify.interfaces.power.on')

        self.assertEqual('poweredOn', vm().summary.runtime.powerState)

        # powering on off twice in a row should not change state.
        exec_op('cloudify.interfaces.power.on')

        self.assertEqual('poweredOn', vm().summary.runtime.powerState)

    def test_power_reset(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.power_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.power_env,
        )

        self.power_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.power_env.execute(
            'execute_operation',
            parameters={
                'node_ids': 'testserver',
                'operation': 'reset',
            },
            task_retries=10,
            task_retry_interval=3,
        )

        vm = self.get_vim_object(
            vim.VirtualMachine,
            self.power_env.storage.get_node_instances('testserver')
            [0].runtime_properties['name'],
        )

        self.assertEqual('poweredOn', vm.summary.runtime.powerState)

    def test_power_reboot(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.power_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.power_env,
        )

        self.power_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.power_env.execute(
            'execute_operation',
            parameters={
                'node_ids': 'testserver',
                'operation': 'cloudify.interfaces.power.reboot',
            },
            task_retries=10,
            task_retry_interval=3,
        )

        vm = self.get_vim_object(
            vim.VirtualMachine,
            self.power_env.storage.get_node_instances('testserver')
            [0].runtime_properties['name'],
        )

        self.assertEqual('poweredOn', vm.summary.runtime.powerState)

    def test_power_shutdown(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host with name assigned')

        self.power_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.power_env,
        )

        self.power_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.power_env.execute(
            'execute_operation',
            parameters={
                'node_ids': 'testserver',
                'operation': 'shut_down',
            },
            task_retries=10,
            task_retry_interval=3,
        )

        vm = self.get_vim_object(
            vim.VirtualMachine,
            self.power_env.storage.get_node_instances('testserver')
            [0].runtime_properties['name'],
        )

        self.assertEqual('poweredOff', vm.summary.runtime.powerState)

    def _has_non_vmxnet3_nic(self, vm):
        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                if not isinstance(dev, vim.vm.device.VirtualVmxnet3):
                    return True
        # If we didn't find one by now, there isn't one
        return False

    def test_remove_interfaces(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'simple-blueprint.yaml'
        )

        self.logger.info('Deploying linux host to check NIC removal')

        vm = self.get_vim_object(
            vim.VirtualMachine,
            self.env.cloudify_config['linux_template'],
        )
        assert self._has_non_vmxnet3_nic(vm), (
            'Linux template must have at least one non-VMXNet3 network '
            'interface for interface removal test. Please add one, e.g. '
            'an E1000.'
        )

        self.nicremove_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.nicremove_env,
        )

        self.nicremove_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        vm = self.get_vim_object(
            vim.VirtualMachine,
            self.nicremove_env.storage.get_node_instances('testserver')
            [0].runtime_properties['name'],
        )
        assert not self._has_non_vmxnet3_nic(vm), (
            'Deployed VM still has non-VMXNet3 interfaces. It should not.'
        )

    def test_network_name_just_slashes(self):
        self._name_test_template(
            net_name='systest/network',
            connect_name='systest/network',
        )

    def test_network_name_slash_connect_encoded(self):
        self._name_test_template(
            net_name='systest/network',
            connect_name='systest%2fnetwork',
        )

    def test_network_name_encoded_connect_slash(self):
        self._name_test_template(
            net_name='systest%2fnetwork',
            connect_name='systest/network',
        )

    def test_network_name_just_encoded(self):
        self._name_test_template(
            net_name='systest%2fnetwork',
            connect_name='systest%2fnetwork',
        )

    def _name_test_template(self, net_name, connect_name):
        blueprint = os.path.join(
            self.blueprints_path,
            'network-name-blueprint.yaml'
        )

        self.logger.info('Deploying network and linux host for network name '
                         'test')

        inputs = copy(self.ext_inputs)
        if 'test_network_name' in self.env.cloudify_config.keys():
            inputs['test_network_name'] = self.env.cloudify_config[
                'test_network_name']
        if 'test_network_vlan' in self.env.cloudify_config.keys():
            inputs['test_network_vlan'] = self.env.cloudify_config[
                'test_network_vlan']
        if 'test_network_dvswitch' in self.env.cloudify_config.keys():
            inputs['test_network_vswitch'] = self.env.cloudify_config[
                'test_network_dvswitch']
        inputs['test_network_name'] = net_name
        inputs['test_network_connect_name'] = connect_name

        self.network_naming_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.network_naming_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(
            self.generic_cleanup,
            self.network_naming_env,
        )

        network_id = self.network_naming_env.outputs()['network_id']
        vm_id = self.network_naming_env.outputs()['vm_id']
        name = self.get_object_name(
            type=vim.Network,
            id=network_id,
        )

        self.assertEqual(urllib.unquote(net_name), name)
        assert self.vm_has_net(vm_id, network_id)

    def test_empty_custom_attributes(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'custom-attributes-blueprint.yaml'
        )
        inputs = copy(self.ext_inputs)

        self.custom_attrs_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.custom_attrs_env,
        )

        self.custom_attrs_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        with self.platform() as client:
            vm = client._get_obj_by_name(
                vim.VirtualMachine,
                self.custom_attrs_env.storage.get_node_instances('testserver')
                [0].runtime_properties['name'],
            )

            self.assertEqual(0, len(vm.obj.customValue))

    def test_existing_custom_attributes(self):
        with self.platform() as client:
            field = client.si.content.customFieldsManager.AddCustomFieldDef(
                name='test_field_name')
            self.addCleanup(
                self.run_platform_command,
                ['si', 'content',
                 'customFieldsManager', 'RemoveCustomFieldDef'],
                key=field.key
            )

        blueprint = os.path.join(
            self.blueprints_path,
            'custom-attributes-blueprint.yaml'
        )
        inputs = copy(self.ext_inputs)
        inputs['custom_attributes'] = {
            'test_field_name': 'test_value',
        }
        self.custom_attrs_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.custom_attrs_env,
        )

        self.custom_attrs_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        with self.platform() as client:
            vm = client._get_obj_by_name(
                vim.VirtualMachine,
                self.custom_attrs_env.storage.get_node_instances('testserver')
                [0].runtime_properties['name'],
            )

            self.assertEqual(1, len(vm.obj.customValue))

            for item in vm.obj.customValue:
                if item.key == field.key and item.value == 'test_value':
                    break
            else:
                raise AssertionError(
                    "matching custom attribute for {}: {} not found".format(
                        field.key, item.value))

    def test_new_custom_attributes(self):
        def get_new_field_key(name):
            with self.platform() as client:
                for key in client.si.content.customFieldsManager.field:
                    if key.name == name:
                        return key.key
            raise KeyError("Key not found: {}".format(name))

        blueprint = os.path.join(
            self.blueprints_path,
            'custom-attributes-blueprint.yaml'
        )
        inputs = copy(self.ext_inputs)
        inputs['custom_attributes'] = {
            'test_field_name': 'test_value',
        }
        self.custom_attrs_env = local.init_env(
            blueprint,
            inputs=inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(
            self.generic_cleanup,
            self.custom_attrs_env,
        )

        self.custom_attrs_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(
            self.run_platform_command,
            ['si', 'content',
             'customFieldsManager', 'RemoveCustomFieldDef'],
            key=get_new_field_key('test_field_name')
        )

        with self.platform() as client:
            vm = client._get_obj_by_name(
                vim.VirtualMachine,
                self.custom_attrs_env.storage.get_node_instances('testserver')
                [0].runtime_properties['name'],
            )

            self.assertEqual(1, len(vm.obj.customValue))

            field = next(
                key
                for key in client.si.content.customFieldsManager.field
                if key.name == 'test_field_name')

            for item in vm.obj.customValue:
                if item.key == field.key and item.value == 'test_value':
                    break
            else:
                raise AssertionError(
                    "matching custom attribute for {}: {} not found".format(
                        field.key, item.value))

    def generic_cleanup(self, component):
        component.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    @contextmanager
    def platform(self):
        with PlatformCaller(
            host=self.ext_inputs['vsphere_host'],
            port=self.ext_inputs['vsphere_port'],
            username=self.ext_inputs['vsphere_username'],
            password=self.ext_inputs['vsphere_password'],
        ) as client:
            yield client

    def get_vim_object(self, type, name):
        with self.platform() as client:
            return client._get_obj_by_name(type, name)

    def get_object_name(self, type, id):
        with self.platform() as client:
            result = client._get_obj_by_id(type, id)
            objs = client._get_getter_method(type)()
            assert hasattr(result, 'name'), (
                'Could not find object of type {type} with ID {id}. '
                'Available were: {objs}'.format(
                    type=type,
                    id=id,
                    objs=objs,
                )
            )
            return result.name

    def vm_has_net(self, vm_id, net_id):
        with self.platform() as client:
            vm = client._get_obj_by_id(vim.VirtualMachine, vm_id)
        for net in vm.network:
            if net.id == net_id:
                return True
        return False

    def run_platform_command(self, command, *args, **kwargs):
        with self.platform() as client:
            comm = client
            for part in command:
                comm = getattr(comm, part)
            return comm(*args, **kwargs)
