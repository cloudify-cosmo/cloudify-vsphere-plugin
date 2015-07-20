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

import atexit
import os
import pyVmomi
import random

from pyVim.connect import SmartConnect, Disconnect

from cosmo_tester.framework import handlers

vim = pyVmomi.vim
vmodl = pyVmomi.vmodl


class VsphereCleanupContext(handlers.BaseHandler.CleanupContext):

    def __init__(self, context_name, env):
        super(VsphereCleanupContext, self).__init__(context_name, env)
        self.get_vsphere_state()
        self.si = SmartConnect(host=self.env.vsphere_url,
                               user=self.env.vsphere_username,
                               pwd=self.env.vsphere_password,
                               port=443)
        atexit.register(Disconnect, self.si)

    def cleanup(self):
        """Cleans resources according to the resource pool they run under.
        """
        super(VsphereCleanupContext, self).cleanup()
        # prints all the resources
        self.get_vsphere_state()
        if self.skip_cleanup:
            self.logger.warn('[{0}] SKIPPING cleanup: of the resources.'
                             .format(self.context_name))
            return
        results = self._get_obj_list([vim.VirtualMachine], self.si)

        for result in results:
            if result.resourcePool and \
               result.resourcePool.name == 'system_tests':
                print('DELETING: %s' % result.name)
                result.Destroy()
            else:
                print('Leaving %s' % result.name)

    def _get_obj_list(vimtype, si):
        content = si.RetrieveContent()
        container_view = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True
        )
        objects = container_view.view
        container_view.Destroy()
        return objects

    def get_vsphere_state(self):
        vms = self.env.handler.get_all_vms(self.si)
        for vm in vms:
            self.env.handler.print_vm_info(vm)
        return vms


class CloudifyVsphereInputsConfigReader(handlers.
                                        BaseCloudifyInputsConfigReader):

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
    def vsphere_host(self):
        return self.config['vsphere_host']

    @property
    def management_network_name(self):
        return self.config['management_network_name']

    @property
    def external_network_name(self):
        return self.config['external_network_name']


class VsphereHandler(handlers.BaseHandler):

    CleanupContext = VsphereCleanupContext
    CloudifyConfigReader = CloudifyVsphereInputsConfigReader

    def __init__(self, env):
        super(VsphereHandler, self).__init__(env)
        # plugins_branch should be set manually when running locally!
        self.plugins_branch = os.environ.get('BRANCH_NAME_PLUGINS', '1.2')
        self.env = env

    def before_bootstrap(self):
        super(VsphereHandler, self).before_bootstrap()
        with self.update_cloudify_config() as patch:
            suffix = '-%06x' % random.randrange(16 ** 6)
            patch.append_value('manager_server_name', suffix)

    def print_vm_info(self, vm, depth=1, max_depth=10):
        """Print information for a particular virtual machine or recurse into a
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
        print("Name       : ", summary.config.name)
        print("Path       : ", summary.config.vmPathName)
        print("Guest      : ", summary.config.guestFullName)
        annotation = summary.config.annotation
        if annotation:
            print("Annotation : ", annotation)
        print("State      : ", summary.runtime.powerState)
        if summary.guest is not None:
            ip = summary.guest.ipAddress
            if ip:
                print("IP         : ", ip)
        if summary.runtime.question is not None:
            print("Question  : ", summary.runtime.question.text)
        print("")

    def get_all_vms(self, si):
        return self.get_vm_by_name(si, '')

    @staticmethod
    def get_vms_by_prefix(si, vm_name, prefix_enabled):
        vms = []
        try:
            atexit.register(Disconnect, si)
            content = si.RetrieveContent()
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
            print("Caught vmodl fault : " + error.msg)
            return

        object_view.Destroy()
        return vms

    def get_vm_by_name(self, si, vm_name):
        return self.get_vms_by_prefix(si, vm_name, False)


handler = VsphereHandler
has_manager_blueprint = True
