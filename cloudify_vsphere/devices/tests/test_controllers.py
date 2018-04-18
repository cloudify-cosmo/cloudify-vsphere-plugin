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
from mock import MagicMock, Mock, patch

from pyVmomi import vim

from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext
from cloudify.exceptions import NonRecoverableError

from cloudify_vsphere import devices


class VsphereControllerTest(unittest.TestCase):

    def tearDown(self):
        current_ctx.clear()
        super(VsphereControllerTest, self).tearDown()

    def _gen_ctx(self):
        _ctx = MockCloudifyContext(
            'node_name',
            properties={},
            runtime_properties={}
        )

        _ctx._execution_id = "execution_id"
        _ctx.instance.host_ip = None

        current_ctx.set(_ctx)
        return _ctx

    def _gen_relation_ctx(self):
        _target = MockCloudifyContext(
            'target',
            properties={},
            runtime_properties={}
        )
        _source = MockCloudifyContext(
            'source',
            properties={},
            runtime_properties={}
        )

        _ctx = MockCloudifyContext(
            target=_target,
            source=_source
        )

        _ctx._source.node.properties["connection_config"] = {
            "username": "vcenter_user",
            "password": "vcenter_password",
            "host": "vcenter_ip",
            "port": 443,
            "datacenter_name": "vcenter_datacenter",
            "resource_pool_name": "vcenter_resource_pool",
            "auto_placement": "vsphere_auto_placement",
            "allow_insecure": True
        }
        current_ctx.set(_ctx)
        return _ctx

    def test_create_contoller(self):
        _ctx = self._gen_ctx()
        devices.create_contoller(ctx=_ctx, a="b")
        self.assertEqual(_ctx.instance.runtime_properties, {"a": "b"})

    def test_delete_contoller(self):
        _ctx = self._gen_ctx()
        _ctx.instance.runtime_properties["c"] = "d"
        devices.delete_contoller(ctx=_ctx)
        self.assertEqual(_ctx.instance.runtime_properties, {})

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

    def test_detach_contoller(self):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.SmartConnectNoSSL", smart_connect):
            with patch("vsphere_plugin_common.Disconnect", Mock()):
                # without vm-id
                with self.assertRaises(NonRecoverableError) as e:
                    devices.detach_contoller(ctx=_ctx)
                self.assertEqual(e.exception.message, "VM is not defined")

                # without device key
                _ctx.target.instance.runtime_properties[
                    'vsphere_server_id'
                ] = "vm-101"
                with self.assertRaises(NonRecoverableError) as e:
                    devices.detach_contoller(ctx=_ctx)
                self.assertEqual(e.exception.message,
                                 "Device Key is not defined")

                # no such device
                _ctx.source.instance.runtime_properties['busKey'] = 4010
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.detach_contoller(ctx=_ctx)
                self.assertEqual(
                    _ctx.source.instance.runtime_properties, {}
                )

                # we have such device
                _ctx.source.instance.runtime_properties['busKey'] = 4001
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.detach_contoller(ctx=_ctx)
                self.assertEqual(
                    _ctx.source.instance.runtime_properties, {}
                )

    def check_attach_ethernet_card(self, settings):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.SmartConnectNoSSL", smart_connect):
            with patch("vsphere_plugin_common.Disconnect", Mock()):
                # use unexisted network
                _ctx.source.instance.runtime_properties.update(settings)
                network = None
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_ethernet_card(ctx=_ctx)
                    self.assertEqual(e.exception.message,
                                     "Network Cloudify could not be found")

                # without vm-id / distributed
                _ctx.source.instance.runtime_properties[
                    'switch_distributed'
                ] = True
                network = Mock()
                network.obj = network
                network.config.distributedVirtualSwitch.uuid = "aa-bb-vv"
                network.key = "121"
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_ethernet_card(ctx=_ctx)
                    self.assertEqual(e.exception.message,
                                     "VM is not defined")

                # without vm-id / simple network
                _ctx.source.instance.runtime_properties[
                    'switch_distributed'
                ] = False
                network = vim.Network("Cloudify")
                network.obj = network
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_ethernet_card(ctx=_ctx)
                    self.assertEqual(e.exception.message,
                                     "VM is not defined")

                # issues with add device
                _ctx.target.instance.runtime_properties[
                    'vsphere_server_id'
                ] = "vm-101"
                network = vim.Network("Cloudify")
                network.obj = network
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with patch(
                        "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                        MagicMock(return_value=network)
                    ):
                        with self.assertRaises(NonRecoverableError) as e:
                            devices.attach_ethernet_card(ctx=_ctx)
                        self.assertEqual(
                            e.exception.message,
                            "Have not found key for new added device")

    def test_attach_ethernet_card(self):
        for settings in [{
            'adapter_type': None,
            'name': "Cloudify"
        }, {
            'adapter_type': "E1000e",
            'name': "Cloudify"
        }, {
            'adapter_type': "E1000",
            'name': "Cloudify"
        }, {
            'adapter_type': "Sriov",
            'name': "Cloudify",
            'mac_address': "aa:bb:cc:dd"
        }, {
            'adapter_type': "Vmxnet2",
            'name': "Cloudify",
            'network_connected': False
        }]:
            self.check_attach_ethernet_card(settings)

    def check_attach_scsi_contoller(self, settings):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.SmartConnectNoSSL", smart_connect):
            with patch("vsphere_plugin_common.Disconnect", Mock()):
                # without vm-id
                with self.assertRaises(NonRecoverableError) as e:
                    devices.attach_scsi_contoller(ctx=_ctx)
                self.assertEqual(e.exception.message, "VM is not defined")

                # with vm-id, not relly attached device
                _ctx.target.instance.runtime_properties[
                    'vsphere_server_id'
                ] = "vm-101"
                vm = self._get_vm()
                _ctx.source.instance.runtime_properties.update(settings)
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_scsi_contoller(ctx=_ctx)
                    self.assertEqual(e.exception.message,
                                     "Have not found key for new added device")

    def test_attach_scsi_contoller(self):
        for settings in [{
           'adapterType': None,
           'label': "Cloudify",
           'hotAddRemove': False,
           "sharedBus": "virtualSharing"
        }, {
           'adapterType': "lsilogic",
           'label': "Cloudify",
           "scsiCtlrUnitNumber": 100,
           "sharedBus": "physicalSharing"
        }, {
           'adapterType': "lsilogic_sas",
           'label': "Cloudify",
           'hotAddRemove': True
        }]:
            self.check_attach_scsi_contoller(settings)
