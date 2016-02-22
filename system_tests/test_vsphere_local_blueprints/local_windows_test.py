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

import os
import socket
import time

from cosmo_tester.framework.testenv import TestCase
from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
import winrm
from . import (
    get_vsphere_vms_list,
    check_correct_vm_name,
    get_runtime_props,
    check_vm_name_in_runtime_properties,
)


class VsphereLocalWindowsTest(TestCase):
    def setUp(self):
        super(VsphereLocalWindowsTest, self).setUp()
        self.ext_inputs = {
            'vm_password': self.env.cloudify_config['vm_password'],
            'template_name': self.env.cloudify_config['windows_template'],
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

        # Expecting the blueprint in ../resources/windows, e.g.
        # ../resources/windows/password_and_timezone.yaml
        blueprints_path = os.path.split(os.path.abspath(__file__))[0]
        blueprints_path = os.path.split(blueprints_path)[0]
        self.blueprints_path = os.path.join(
            blueprints_path,
            'resources',
            'windows'
        )

    def test_no_password_fails(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'no_password-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying windows host with no password set')

        self.no_password_fail_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        try:
            self.no_password_fail_env.execute('install')
            self.no_password_fail_env.execute('uninstall', task_retries=50)
            raise AssertionError(
                'Windows deployment should fail with no password, '
                'but it succeeded.'
            )
        except RuntimeError as err:
            # Ensure the error message has pertinent information
            assert 'Windows' in err.message
            assert 'password must be set' in err.message
            assert 'properties.windows_password' in err.message
            assert 'properties.agent_config.password' in err.message
            self.logger.info('Windows passwordless deploy has correct error.')

    def test_password_and_timezone(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'password_and_timezone-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info(
            'Deploying windows host with '
            'password and timezone set'
        )

        self.password_and_timezone_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.password_and_timezone_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_password_and_timezone)

        vm_ip = self.password_and_timezone_env.outputs()['vm_ip']
        vm_password = self.ext_inputs['vm_password']

        self.check_vm_timezone_offset_is(
            offset=-7,
            vm_ip=vm_ip,
            vm_password=vm_password,
        )

    def test_agent_config_password_and_default_timezone(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'agent_config_password_and_default_timezone-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info(
            'Deploying windows host with '
            'agent_config password and no timezone set'
        )

        self.agent_config_password_and_no_timezone_env = local.init_env(
            blueprint,
            inputs=self.ext_inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)
        self.agent_config_password_and_no_timezone_env.execute(
            'install',
            task_retries=50,
            task_retry_interval=3,
        )

        self.addCleanup(self.cleanup_agent_config_password_and_no_timezone)

    def test_naming(self):
        blueprint = os.path.join(
            self.blueprints_path,
            'naming-blueprint.yaml'
        )

        if self.env.install_plugins:
            self.logger.info('installing required plugins')
            self.cfy.install_plugins_locally(
                blueprint_path=blueprint)

        self.logger.info('Deploying windows host without name assigned')

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
            target_node_id='aaaaaaaaaaaaaaaaaaaaaa',
            node_instances=self.naming_env.storage.get_node_instances(),
            logger=self.logger,
        )

        name_prefix = 'aaaaaaaa'
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

    def check_vm_timezone_offset_is(self, offset, vm_ip, vm_password):
        timezone_info = None
        retries = 0

        self.logger.info('Trying to retrieve timezone info')
        # Huge retry to allow Windows to finish sysprep+reboot
        while timezone_info is None and retries <= 100:
            try:
                winrmsession = winrm.Session(
                    vm_ip,
                    auth=(
                        'Administrator',
                        vm_password
                    )
                )
                winrm_result = winrmsession.run_ps(
                    "[TimeZoneInfo]::Local | "
                    "select-object -expandproperty BaseUtcOffset"
                )
                self.logger.info(winrm_result)
                timezone_info = winrm_result.std_out.splitlines()
                self.logger.info(timezone_info)
            except winrm.exceptions.WinRMTransportError:
                self.logger.info('Waiting for server response...')
                time.sleep(10)
                retries += 1
            except socket.error:
                # These can also occur at some points in the Windows startup
                self.logger.info('Waiting for server response...')
                time.sleep(10)
                retries += 1

        assert timezone_info is not None

        self.logger.info('Looking for hours offset')
        hours = None
        for line in timezone_info:
            split_line = line.split(':')
            if len(split_line) == 2:
                key, value = split_line
            else:
                continue
            self.logger.debug('Saw {line}'.format(line=line))
            if key.strip() == 'Hours':
                hours = int(value.strip())
                self.logger.info(
                    'Hours offset found: {hours}'.format(
                        hours=hours
                    )
                )
                break

        assert hours == offset
        self.logger.info('Offset was correct!')

    def cleanup_naming(self):
        self.naming_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_password_and_timezone(self):
        self.password_and_timezone_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )

    def cleanup_agent_config_password_and_no_timezone(self):
        self.agent_config_password_and_no_timezone_env.execute(
            'uninstall',
            task_retries=50,
            task_retry_interval=3,
        )
