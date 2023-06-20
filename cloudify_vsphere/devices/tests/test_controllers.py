# Copyright (c) 2018-2020 Cloudify Platform Ltd. All rights reserved
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
from cloudify.manager import DirtyTrackingDict
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

        _ctx._source.instance._runtime_properties = DirtyTrackingDict({})
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
        _ctx._target.instance._runtime_properties = DirtyTrackingDict({})
        _ctx._target.node.properties["connection_config"] = {
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

    def _get_vm(self, new_adapter=None):
        vm = Mock()
        task = Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.ReconfigVM_Task = MagicMock(return_value=task)
        vm.guest.net = []
        contr_device = vim.vm.device.VirtualController()
        contr_device.key = 4001
        contr_device.busNumber = 2
        net_device = vim.vm.device.VirtualVmxnet3()
        net_device.key = 4002
        scsi_device = vim.vm.device.ParaVirtualSCSIController()
        scsi_device.key = 4003
        devices = [contr_device, net_device, scsi_device]
        if new_adapter:
            new_adapter.key = 4004
            devices.append(new_adapter)
        vm.config.hardware.device = devices
        return vm

    def test_create_controller(self):
        _ctx = self._gen_ctx()
        _ctx.node._type = "cloudify.vsphere.nodes.NIC"
        devices.create_controller(ctx=_ctx, a="b")
        self.assertEqual(_ctx.instance.runtime_properties, {"a": "b"})

    def test_delete_controller(self):
        _ctx = self._gen_ctx()
        _ctx.instance.runtime_properties["c"] = "d"
        devices.delete_controller(ctx=_ctx)
        self.assertEqual(_ctx.instance.runtime_properties, {})

    def test_detach_controller(self):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.clients.SmartConnectNoSSL",
                   smart_connect):
            with patch("vsphere_plugin_common.clients.Disconnect", Mock()):
                # without vm-id
                _ctx.source.instance.runtime_properties['busKey'] = 4010
                with self.assertRaises(NonRecoverableError) as e:
                    devices.detach_controller(ctx=_ctx)
                self.assertEqual(str(e.exception), "VM is not defined")

                # no such device
                _ctx.source.instance.runtime_properties['busKey'] = 4010
                _ctx.target.instance.runtime_properties[
                    'vsphere_server_id'
                ] = "vm-101"
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.detach_controller(ctx=_ctx)
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
                    devices.detach_controller(ctx=_ctx)
                self.assertEqual(
                    _ctx.source.instance.runtime_properties, {}
                )

                # rerun
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.detach_controller(ctx=_ctx)
                self.assertEqual(
                    _ctx.source.instance.runtime_properties, {}
                )

    def test_detach_server_from_controller(self):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.clients.SmartConnectNoSSL",
                   smart_connect):
            with patch("vsphere_plugin_common.clients.Disconnect", Mock()):
                # reinstall with empty properties
                devices.detach_server_from_controller(ctx=_ctx)

                # real delte conteroller
                _ctx.source.instance.runtime_properties[
                    'vsphere_server_id'
                ] = "vm-101"
                _ctx.target.instance.runtime_properties['busKey'] = 4010
                vm = self._get_vm()
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.detach_server_from_controller(ctx=_ctx)

    def check_attach_ethernet_card(self, settings):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.clients.SmartConnectNoSSL",
                   smart_connect):
            with patch("vsphere_plugin_common.clients.Disconnect", Mock()):
                # use unexisted network
                _ctx.source.instance.runtime_properties.update(settings)
                network = None
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_ethernet_card(ctx=_ctx)
                    self.assertEqual(str(e.exception),
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
                    self.assertEqual(str(e.exception),
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
                    self.assertEqual(str(e.exception),
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
                            str(e.exception),
                            "Have not found key for new added device")
                args, kwargs = vm.obj.ReconfigVM_Task.call_args
                self.assertEqual(args, ())
                self.assertEqual(list(kwargs.keys()), ['spec'])
                new_adapter = str(
                    type(kwargs['spec'].deviceChange[0].device))
                runtime_properties = _ctx.target.instance.runtime_properties

                if settings.get('adapter_type'):
                    self.assertTrue(
                        settings['adapter_type'].lower() in new_adapter.lower()
                    )
                    if "virtualvmxnet3" in new_adapter.lower():
                        self.assertEqual(
                            runtime_properties.get('known_keys'),
                            [4002]
                        )
                    else:
                        self.assertFalse(runtime_properties.get('known_keys'))
                else:
                    self.assertEqual(
                        new_adapter,
                        "<class 'pyVmomi.VmomiSupport.vim.vm.device."
                        "VirtualVmxnet3'>")

                # successful attach
                runtime_properties = _ctx.target.instance.runtime_properties
                runtime_properties['connected_networks'] = False
                runtime_properties['connected'] = False
                runtime_properties['known_keys'] = [4001, 4002, 4003]
                vm = self._get_vm(kwargs['spec'].deviceChange[0].device)
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with patch(
                        "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                        MagicMock(return_value=network)
                    ):
                        devices.attach_ethernet_card(ctx=_ctx)

                # rerun ignore
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with patch(
                        "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                        MagicMock(return_value=network)
                    ):
                        devices.attach_ethernet_card(ctx=_ctx)

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

    def check_attach_scsi_controller(self, settings):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.clients.SmartConnectNoSSL",
                   smart_connect):
            with patch("vsphere_plugin_common.clients.Disconnect", Mock()):
                # without vm-id
                with self.assertRaises(NonRecoverableError) as e:
                    devices.attach_scsi_controller(ctx=_ctx)
                self.assertEqual(str(e.exception), "VM is not defined")

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
                        devices.attach_scsi_controller(ctx=_ctx)
                    self.assertEqual(str(e.exception),
                                     "Have not found key for new added device")
                args, kwargs = vm.obj.ReconfigVM_Task.call_args
                self.assertEqual(args, ())
                self.assertEqual(list(kwargs.keys()), ['spec'])
                new_adapter = str(type(kwargs['spec'].deviceChange[0].device))
                runtime_properties = _ctx.source.instance.runtime_properties
                if settings.get('adapterType') == "lsilogic":
                    self.assertEqual(
                        new_adapter,
                        "<class 'pyVmomi.VmomiSupport.vim.vm.device."
                        "VirtualLsiLogicController'>"
                    )
                    self.assertFalse(runtime_properties.get('known_keys'))
                elif settings.get('adapterType') == "lsilogic_sas":
                    self.assertEqual(
                        new_adapter,
                        "<class 'pyVmomi.VmomiSupport.vim.vm.device."
                        "VirtualLsiLogicSASController'>"
                    )
                    self.assertFalse(runtime_properties.get('known_keys'))
                else:
                    self.assertEqual(
                        new_adapter,
                        "<class 'pyVmomi.VmomiSupport.vim.vm.device."
                        "ParaVirtualSCSIController'>"
                    )
                    self.assertEqual(
                        runtime_properties.get('known_keys'), [4003]
                    )

                # successful attach
                runtime_properties = _ctx.source.instance.runtime_properties
                runtime_properties['connected_networks'] = False
                runtime_properties['connected'] = False
                runtime_properties['known_keys'] = [4003]
                vm = self._get_vm(kwargs['spec'].deviceChange[0].device)
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.attach_scsi_controller(ctx=_ctx)

                # rerun ignore
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    devices.attach_scsi_controller(ctx=_ctx)

    def test_attach_scsi_controller(self):
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
            self.check_attach_scsi_controller(settings)

    def check_attach_server_ethernet_card(self, settings):
        _ctx = self._gen_relation_ctx()
        conn_mock = Mock()
        smart_connect = MagicMock(return_value=conn_mock)
        with patch("vsphere_plugin_common.clients.SmartConnectNoSSL",
                   smart_connect):
            with patch("vsphere_plugin_common.clients.Disconnect", Mock()):
                # use unexisted network
                _ctx.target.instance.runtime_properties.update(settings)
                network = None
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_server_to_ethernet_card(ctx=_ctx)
                    self.assertEqual(str(e.exception),
                                     "Network Cloudify could not be found")

                # without vm-id / distributed
                _ctx.target.instance.runtime_properties[
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
                        devices.attach_server_to_ethernet_card(ctx=_ctx)
                    self.assertEqual(str(e.exception),
                                     "VM is not defined")

                # without vm-id / simple network
                _ctx.target.instance.runtime_properties[
                    'switch_distributed'
                ] = False
                network = vim.Network("Cloudify")
                network.obj = network
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                    MagicMock(return_value=network)
                ):
                    with self.assertRaises(NonRecoverableError) as e:
                        devices.attach_server_to_ethernet_card(ctx=_ctx)
                    self.assertEqual(str(e.exception),
                                     "VM is not defined")

                # issues with add device
                _ctx.source.instance.runtime_properties[
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
                            devices.attach_server_to_ethernet_card(ctx=_ctx)
                        self.assertEqual(
                            str(e.exception),
                            "Have not found key for new added device")

                args, kwargs = vm.obj.ReconfigVM_Task.call_args
                self.assertEqual(args, ())
                self.assertEqual(list(kwargs.keys()), ['spec'])

                # successful attach
                runtime_properties = _ctx.target.instance.runtime_properties
                runtime_properties['connected_networks'] = False
                runtime_properties['connected'] = False
                runtime_properties['known_keys'] = [4003]
                vm = self._get_vm(kwargs['spec'].deviceChange[0].device)
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with patch(
                        "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                        MagicMock(return_value=network)
                    ):
                        devices.attach_server_to_ethernet_card(ctx=_ctx)

                # rerun ignore
                with patch(
                    "vsphere_plugin_common.VsphereClient._get_obj_by_id",
                    MagicMock(return_value=vm)
                ):
                    with patch(
                        "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                        MagicMock(return_value=network)
                    ):
                        devices.attach_server_to_ethernet_card(ctx=_ctx)

    def test_attach_server_ethernet_card(self):
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
            self.check_attach_server_ethernet_card(settings)


if __name__ == '__main__':
    unittest.main()
