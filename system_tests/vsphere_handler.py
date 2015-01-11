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
import random
import time
import atexit

from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim

from cosmo_tester.framework.handlers import (BaseHandler,
                                             BaseCloudifyInputsConfigReader)


class VsphereCleanupContext(BaseHandler.CleanupContext):

    def __init__(self, context_name, env):
        super(VsphereCleanupContext, self).__init__(context_name, env)
        self.get_vsphere_state()

    def cleanup(self):
        """
        Cleans resources by prefix in order to allow working
        on vsphere env while testing - need to add clean by prefix
        once CFY-1827 is fixed.

        It should be noted that cleanup is not implemented in any manner
        at the moment. if things fail, someone should remove resources
        manually
        """
        super(VsphereCleanupContext, self).cleanup()
        if self.skip_cleanup:
            self.logger.warn('SKIPPING cleanup: of the resources')
            return
        self.get_vsphere_state()

    def get_vsphere_state(self):
        vms = self.env.handler.get_all_vms(self.env.vsphere_url,
                                           self.env.vsphere_username,
                                           self.env.vsphere_password,
                                           '443')
        for vm in vms:
            self.env.handler.print_vm_info(vm)
        return vms


class CloudifyVsphereInputsConfigReader(BaseCloudifyInputsConfigReader):

    def __init__(self, cloudify_config, manager_blueprint_path, **kwargs):
        super(CloudifyVsphereInputsConfigReader, self).__init__(
            cloudify_config, manager_blueprint_path=manager_blueprint_path,
            **kwargs)

    @property
    def management_server_name(self):
        return self.config['manager_server_name']

    @property
    def agent_key_path(self):
        return self.config['agent_private_key_path']

    @property
    def management_user_name(self):
        return self.config['manager_server_user']

    @property
    def management_key_path(self):
        return self.config['manager_private_key_path']

    @property
    def vsphere_username(self):
        return self.config['vsphere_username']

    @property
    def vsphere_password(self):
        return self.config['vsphere_password']

    @property
    def vsphere_datacenter_name(self):
        return self.config['vsphere_datacenter_name']

    @property
    def vsphere_url(self):
        return self.config['vsphere_url']

    @property
    def management_network_name(self):
        return self.config['management_network_name']

    @property
    def external_network_name(self):
        return self.config['external_network_name']


class VsphereHandler(BaseHandler):

    CleanupContext = VsphereCleanupContext
    CloudifyConfigReader = CloudifyVsphereInputsConfigReader

    def __init__(self, env):
        super(VsphereHandler, self).__init__(env)
        # plugins_branch should be set manually when running locally!
        self.plugins_branch = os.environ.get('BRANCH_NAME_PLUGINS', '1.1')
        self.env = env

    def before_bootstrap(self):
        super(VsphereHandler, self).before_bootstrap()
        with self.update_cloudify_config() as patch:
            suffix = '-%06x' % random.randrange(16 ** 6)
            patch.append_value('manager_server_name', suffix)

    def get_vm(self, name):
        vms = self.get_vm_by_name(self.env.vsphere_url,
                                  self.env.vsphere_username,
                                  self.env.vsphere_password,
                                  '443',
                                  name)
        for vm in vms:
            self.print_vm_info(vm)
        return vms

    def print_vm_info(self, vm, depth=1, max_depth=10):
        """
        Print information for a particular virtual machine or recurse into a
        folder with depth protection
        """
        # if this is a group it will have children. if it does, recurse into
        # them and then return
        if hasattr(vm, 'childEntity'):
            if depth > max_depth:
                return
            vmList = vm.childEntity
            for c in vmList:
                self.print_vm_info(c, depth + 1)
            return

        summary = vm.summary
        print "Name       : ", summary.config.name
        print "Path       : ", summary.config.vmPathName
        print "Guest      : ", summary.config.guestFullName
        annotation = summary.config.annotation
        if annotation:
            print "Annotation : ", annotation
        print "State      : ", summary.runtime.powerState
        if summary.guest is not None:
            ip = summary.guest.ipAddress
            if ip:
                print "IP         : ", ip
        if summary.runtime.question is not None:
            print "Question  : ", summary.runtime.question.text
        print ""

    @staticmethod
    def is_vm_poweredon(vm):
        return vm.summary.runtime.powerState.lower() == "poweredon"

    @staticmethod
    def wait_for_task(task):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(15)
        if not task.info.state == vim.TaskInfo.State.success:
            raise task.info.error

    # TODO check if before poweroff should connect
    def terminate_vm(self, vm):
        if self.is_vm_poweredon(vm):
            task = vm.PowerOff()
            self.wait_for_task(task)
            task = vm.Destroy()
            self.wait_for_task(task)

    def get_all_vms(self, host, user, pwd, port):
        return self.get_vm_by_name(host, user, pwd, port, '')

    @staticmethod
    def get_vms_by_prefix(host, user, pwd, port, vm_name, prefix_enabled):
        vms = []
        try:
            service_instance = connect.SmartConnect(host=host,
                                                    user=user,
                                                    pwd=pwd,
                                                    port=int(port))
            atexit.register(connect.Disconnect, service_instance)
            content = service_instance.RetrieveContent()
            object_view = content.viewManager. \
                CreateContainerView(content.rootFolder, [], True)
            for obj in object_view.view:
                if isinstance(obj, vim.VirtualMachine):
                    if obj.summary.config.name == vm_name \
                            or vm_name == '' \
                            or (prefix_enabled and
                                obj.summary.config.name.startswith(vm_name)):
                        vms.append(obj)
        except vmodl.MethodFault as error:
            print "Caught vmodl fault : " + error.msg
            return

        object_view.Destroy()
        return vms

    def get_vm_by_name(self, host, user, pwd, port, vm_name):
        return self.get_vms_by_prefix(host, user, pwd, port, vm_name, False)


handler = VsphereHandler
has_manager_blueprint = True


def _replace_string_in_file(file_name, old_string, new_string):
    with open(file_name, 'r') as f:
        newlines = []
        for line in f.readlines():
            newlines.append(line.replace(old_string, new_string))
    with open(file_name, 'w') as f:
        for line in newlines:
            f.write(line)


def update_config(manager_blueprints_dir, variables):
    cloudify_automation_token = variables['cloudify_automation_token']
    cloudify_automation_token_place_holder = '{CLOUDIFY_AUTOMATION_TOKEN}'
    # used by test
    os.environ['CLOUDIFY_AUTOMATION_TOKEN'] = cloudify_automation_token
    plugin_path = manager_blueprints_dir + '/plugin.yaml'
    _replace_string_in_file(plugin_path,
                            cloudify_automation_token_place_holder,
                            cloudify_automation_token)
