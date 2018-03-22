# Copyright (c) 2018 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import unittest
from mock import MagicMock, Mock, patch, call
from pyVmomi import vim

from vsphere_plugin_common import ContollerClient


class VsphereDeviceTest(unittest.TestCase):

    def _get_vm(self):
        vm = Mock()
        task = Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.ReconfigVM_Task = MagicMock(return_value=task)
        contr_device = vim.vm.device.VirtualController()
        contr_device.key = 4001
        contr_device.busNumber = 2
        net_device = vim.vm.device.VirtualVmxnet3()
        net_device.key = 4002
        scsi_device = vim.vm.device.ParaVirtualSCSIController()
        scsi_device.key = 4003
        vm.config.hardware.device = [contr_device, net_device, scsi_device]
        return vm

    def test_check_attach_card(self):
        cl = ContollerClient()

        vm_original = self._get_vm()
        vm_get_mock = MagicMock(return_value=vm_original)
        with patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            vm_get_mock
        ):
            scsi_spec, controller_type = cl.generate_scsi_card(
                {'label': "Cloudify"}, 10)
        vm_get_mock.assert_called_once_with(vim.VirtualMachine, 10)
        self.assertEqual(scsi_spec.device.deviceInfo.label, "Cloudify")

        device = controller_type()
        device.key = 1001
        vm_updated = self._get_vm()
        vm_updated.config.hardware.device.append(device)
        vm_get_mock = MagicMock(side_effect=[vm_original, vm_updated])

        with patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            vm_get_mock
        ):
            self.assertEqual(
                cl.attach_controller(10, scsi_spec, controller_type),
                {'busKey': 1001, 'busNumber': 0})
            vm_get_mock.assert_has_calls([
                call(vim.VirtualMachine, 10),
                call(vim.VirtualMachine, 10, use_cache=False)])
