# Copyright (c) 2019 Cloudify Platform Ltd. All rights reserved
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
import mock

from pyVmomi import vim

from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext
from cloudify.exceptions import NonRecoverableError

import vsphere_server_plugin.server as server


class BackupServerTest(unittest.TestCase):

    def tearDown(self):
        current_ctx.clear()
        super(BackupServerTest, self).tearDown()

    def _gen_ctx(self):
        _ctx = MockCloudifyContext(
            'node_name',
            properties={
                "connection_config": {
                    "username": "vcenter_user",
                    "password": "vcenter_password",
                    "host": "vcenter_ip",
                    "port": 443,
                    "datacenter_name": "vcenter_datacenter",
                    "resource_pool_name": "vcenter_resource_pool",
                    "auto_placement": "vsphere_auto_placement",
                    "allow_insecure": True
                }
            },
            runtime_properties={}
        )

        _ctx._execution_id = "execution_id"
        _ctx.instance.host_ip = None

        current_ctx.set(_ctx)
        return _ctx

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_snapshot_create(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # backup for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.snapshot_create(server={"name": "server_name"},
                               os_family="other_os",
                               snapshot_name="snapshot_name",
                               snapshot_incremental=True)

        # backup without name
        ctx.instance.runtime_properties['use_external_resource'] = False
        with self.assertRaisesRegexp(
            NonRecoverableError,
            "Backup name must be provided."
        ):
            server.snapshot_create(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="",
                                   snapshot_incremental=True)

        # usuported backup type, ignore
        server.snapshot_create(server={"name": "server_name"},
                               os_family="other_os",
                               snapshot_name="snapshot",
                               snapshot_incremental=False)

        # nosuch vm
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot backup server - server doesn't exist for node: "
                "node_name"
            ):
                server.snapshot_create(server={"name": "server_name"},
                                       os_family="other_os",
                                       snapshot_name="snapshot",
                                       snapshot_incremental=True)

        # with some vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        # no snapshots
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = []
        vm.obj.CreateSnapshot = mock.Mock(return_value=task)
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.snapshot_create(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="snapshot",
                                   snapshot_incremental=True)
        vm.obj.CreateSnapshot.assert_called_with(
            'snapshot', description=None, memory=False, quiesce=False)

        # no snapshots
        vm.obj.snapshot = None
        vm.obj.CreateSnapshot = mock.Mock(return_value=task)
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.snapshot_create(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="snapshot",
                                   snapshot_incremental=True)
        vm.obj.CreateSnapshot.assert_called_with(
            'snapshot', description=None, memory=False, quiesce=False)

        # with some vm, prexisted snapshots
        vm = mock.Mock()
        snapshot = mock.Mock()
        snapshot.name = "snapshot"
        snapshot.childSnapshotList = []
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = [snapshot]
        vm.obj.CreateSnapshot = mock.Mock(return_value=task)
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Snapshot snapshot already exists."
            ):
                server.snapshot_create(server={"name": "server_name"},
                                       os_family="other_os",
                                       snapshot_name="snapshot",
                                       snapshot_incremental=True)

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_snapshot_apply(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # backup for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.snapshot_apply(server={"name": "server_name"},
                              os_family="other_os",
                              snapshot_name="snapshot_name",
                              snapshot_incremental=True)

        # backup without name
        ctx.instance.runtime_properties['use_external_resource'] = False
        with self.assertRaisesRegexp(
            NonRecoverableError,
            "Backup name must be provided."
        ):
            server.snapshot_apply(server={"name": "server_name"},
                                  os_family="other_os",
                                  snapshot_name="",
                                  snapshot_incremental=True)

        # usuported backup type, ignore
        server.snapshot_apply(server={"name": "server_name"},
                              os_family="other_os",
                              snapshot_name="snapshot",
                              snapshot_incremental=False)

        # nosuch vm
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot restore server - server doesn't exist for node: "
                "node_name"
            ):
                server.snapshot_apply(server={"name": "server_name"},
                                      os_family="other_os",
                                      snapshot_name="snapshot",
                                      snapshot_incremental=True)
        # with some vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.CreateSnapshot = mock.Mock(return_value=task)
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "No snapshots found with name: snapshot."
            ):
                server.snapshot_apply(server={"name": "server_name"},
                                      os_family="other_os",
                                      snapshot_name="snapshot",
                                      snapshot_incremental=True)
        vm.obj.CreateSnapshot.assert_not_called()

        # remove snapshot
        snapshot = mock.Mock()
        snapshot.name = "snapshot"
        snapshot.childSnapshotList = []
        snapshot.snapshot.RevertToSnapshot_Task = mock.Mock(return_value=task)
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = [snapshot]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.snapshot_apply(server={"name": "server_name"},
                                  os_family="other_os",
                                  snapshot_name="snapshot",
                                  snapshot_incremental=True)
        snapshot.snapshot.RevertToSnapshot_Task.assert_called_with()

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_snapshot_delete(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # backup for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.snapshot_delete(server={"name": "server_name"},
                               os_family="other_os",
                               snapshot_name="snapshot_name",
                               snapshot_incremental=True)

        # backup without name
        ctx.instance.runtime_properties['use_external_resource'] = False
        with self.assertRaisesRegexp(
            NonRecoverableError,
            "Backup name must be provided."
        ):
            server.snapshot_delete(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="",
                                   snapshot_incremental=True)

        # usuported backup type, ignore
        server.snapshot_delete(server={"name": "server_name"},
                               os_family="other_os",
                               snapshot_name="snapshot",
                               snapshot_incremental=False)

        # nosuch vm
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot remove backup for server - server doesn't exist "
                "for node: node_name"
            ):
                server.snapshot_delete(server={"name": "server_name"},
                                       os_family="other_os",
                                       snapshot_name="snapshot",
                                       snapshot_incremental=True)
        # with some vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.CreateSnapshot = mock.Mock(return_value=task)
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "No snapshots found with name: snapshot."
            ):
                server.snapshot_delete(server={"name": "server_name"},
                                       os_family="other_os",
                                       snapshot_name="snapshot",
                                       snapshot_incremental=True)
        vm.obj.CreateSnapshot.assert_not_called()

        # remove snapshot
        snapshot = mock.Mock()
        snapshot.name = "snapshot"
        snapshot.childSnapshotList = []
        snapshot.snapshot.RemoveSnapshot_Task = mock.Mock(return_value=task)
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = [snapshot]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.snapshot_delete(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="snapshot",
                                   snapshot_incremental=True)
        snapshot.snapshot.RemoveSnapshot_Task.assert_called_with(True)

        # remove sub snapshot
        snapshot = mock.Mock()
        snapshot.name = "snapshot"
        snapshot.childSnapshotList = []
        snapshotparent = mock.Mock()
        snapshotparent.name = "snapshotparent"
        snapshotparent.childSnapshotList = [snapshot]
        snapshot.snapshot.RemoveSnapshot_Task = mock.Mock(return_value=task)
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = [snapshotparent]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.snapshot_delete(server={"name": "server_name"},
                                   os_family="other_os",
                                   snapshot_name="snapshot",
                                   snapshot_incremental=True)
        snapshot.snapshot.RemoveSnapshot_Task.assert_called_with(True)

        # can't remove snapshot with child
        snapshot = mock.Mock()
        snapshot.name = "snapshot"
        snapshot.childSnapshotList = []
        snapshotparent = mock.Mock()
        snapshotparent.name = "snapshotparent"
        snapshotparent.childSnapshotList = [snapshot]
        snapshot.snapshot.RemoveSnapshot_Task = mock.Mock(return_value=task)
        vm.obj.snapshot = mock.Mock()
        vm.obj.snapshot.rootSnapshotList = [snapshotparent]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Sub snapshots \\[\'snapshot\'\\] found for snapshotparent. "
                "You should remove subsnaphots before remove current."
            ):
                server.snapshot_delete(server={"name": "server_name"},
                                       os_family="other_os",
                                       snapshot_name="snapshotparent",
                                       snapshot_incremental=True)

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_get_state(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # nosuch vm (we have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = 'vm-unknow'
        ctx.instance.runtime_properties[server.NETWORKS] = []
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot get info - server doesn't exist for node: "
                "node_name"
            ):
                server.get_state(server={"name": "server_name"},
                                 os_family="other_os")

        # skip other vm
        vm = mock.Mock()
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertTrue(
                server.get_state(server={"name": "server_name"},
                                 os_family="other"))

        # rerun solaris
        vm = mock.Mock()
        vm.obj.guest.guestState = 'stopped'
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertFalse(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris"))

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_get_state_network(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # nosuch vm (we have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = 'vm-unknow'
        ctx.instance.runtime_properties[server.NETWORKS] = []
        # guest running, ignore no ip
        vm = mock.Mock()
        vm.obj.guest.guestState = 'running'
        vm.guest.net = []
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertTrue(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 networking={}))

        # guest running, check ip
        vm = mock.Mock()
        vm.obj.guest.guestState = 'running'
        vm.guest.net = []
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertFalse(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 wait_ip=True,
                                 networking={}))

        # we have some ip
        vm = mock.Mock()
        vm.obj.guest.guestState = 'running'
        network = mock.Mock()
        network.network = 'some_net'
        network.ipAddress = ["192.0.2.1"]
        vm.guest.net = [network]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertTrue(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 wait_ip=True,
                                 networking={}))
        self.assertEqual(
            ctx.instance.runtime_properties[server.IP], "192.0.2.1")

        # we have some ip
        vm = mock.Mock()
        vm.obj.guest.guestState = 'running'
        network1 = mock.Mock()
        network1.network = 'some_net'
        network1.ipAddress = ["192.0.2.1"]
        network2 = mock.Mock()
        network2.network = 'other_net'
        network2.ipAddress = ["192.0.2.2"]
        vm.guest.net = [network1, network2]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertTrue(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 wait_ip=True,
                                 networking={
                                    'connect_networks': [{
                                        'name': 'other_net',
                                        'management': True
                                     }]
                                }))
        self.assertEqual(
            ctx.instance.runtime_properties[server.IP], "192.0.2.2")

        # no network with management name
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            ctx.operation.retry = mock.Mock(side_effect=Exception('retry?'))
            with self.assertRaisesRegexp(
                Exception,
                'retry?'
            ):
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 wait_ip=True,
                                 networking={
                                    'connect_networks': [{
                                        'name': 'broken',
                                        'management': True
                                     }]
                                })

        # managment network exists by without ip yet
        vm = mock.Mock()
        vm.obj.guest.guestState = 'running'
        network2 = mock.Mock()
        network2.network = 'other_net'
        network2.ipAddress = ["169.254.1.1"]
        vm.guest.net = [network1, network2]
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            self.assertFalse(
                server.get_state(server={"name": "server_name"},
                                 os_family="solaris",
                                 wait_ip=True,
                                 networking={
                                    'connect_networks': [{
                                        'name': 'other_net',
                                        'management': True
                                     }]
                                }))

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_delete(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # delete for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.delete(server={"name": "server_name"},
                      os_family="other_os")

        # nosuch vm (we dont have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = None
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=None)
        ):
            server.delete(server={"name": "server_name"},
                          os_family="other_os")

        # nosuch vm (we have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = 'vm-unknow'
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot delete server - server doesn't exist for node: "
                "node_name"
            ):
                server.delete(server={"name": "server_name"},
                              os_family="other_os")

        # with some vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.Destroy = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOFF"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            server.delete(server={"name": "server_name"},
                          os_family="other_os")
        vm.obj.Destroy.assert_called_with()

        # with some external vm with force action
        ctx.instance.runtime_properties['use_external_resource'] = True
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.Destroy = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOFF"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            with mock.patch(
                "vsphere_plugin_common.VsphereClient._get_obj_by_name",
                mock.Mock(return_value=vm)
            ):
                server.delete(server={"name": "server_name"},
                              os_family="other_os",
                              force_delete=True)
        vm.obj.Destroy.assert_called_with()

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_shutdown_guest(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # shutdown_guest for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot shutdown server guest - server doesn't exist for "
                "node: node_name"
            ):
                server.shutdown_guest(server={"name": "server_name"},
                                      os_family="other_os")

        # nosuch vm
        ctx.instance.runtime_properties['use_external_resource'] = False
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot shutdown server guest - server doesn't exist for "
                "node: node_name"
            ):
                server.shutdown_guest(server={"name": "server_name"},
                                      os_family="other_os")

        # with poweredoff vm
        vm = mock.Mock()
        vm.obj.summary.runtime.powerState = "PoweredOFF"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.shutdown_guest(server={"name": "server_name"},
                                  os_family="other_os")

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_stop(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # stop for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.stop(server={"name": "server_name"},
                    os_family="other_os")

        # nosuch vm (we dont have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = None
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=None)
        ):
            server.stop(server={"name": "server_name"},
                        os_family="other_os")

        # nosuch vm (we have vm_id)
        ctx.instance.runtime_properties['use_external_resource'] = False
        ctx.instance.runtime_properties['vsphere_server_id'] = 'vm-unknow'
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot stop server - server doesn't exist for node: "
                "node_name"
            ):
                server.stop(server={"name": "server_name"},
                            os_family="other_os")

        # with poweredoff vm
        vm = mock.Mock()
        vm.obj.summary.runtime.powerState = "PoweredOFF"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            server.stop(server={"name": "server_name"},
                        os_family="other_os")

        # with poweredoff vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.PowerOff = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOn"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            server.stop(server={"name": "server_name"},
                        os_family="other_os")
        vm.obj.PowerOff.assert_called_with()

        # with poweredoff vm, use exteranl vm with force
        ctx.instance.runtime_properties['use_external_resource'] = True
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.PowerOff = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOn"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_id",
            mock.Mock(return_value=vm)
        ):
            server.stop(server={"name": "server_name"},
                        os_family="other_os",
                        force_stop=True)
        vm.obj.PowerOff.assert_called_with()

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_freeze_suspend(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # suspend for external
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.freeze_suspend(server={"name": "server_name"},
                              os_family="other_os")

        # nosuch vm
        ctx.instance.runtime_properties['use_external_resource'] = False
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot suspend server - server doesn't exist for node: "
                "node_name"
            ):
                server.freeze_suspend(server={"name": "server_name"},
                                      os_family="other_os")

        # with suspended vm
        vm = mock.Mock()
        vm.obj.summary.runtime.powerState = "Suspended"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.freeze_suspend(server={"name": "server_name"},
                                  os_family="other_os")

        # with poweredoff vm
        vm = mock.Mock()
        vm.obj.summary.runtime.powerState = "PoweredOFF"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.freeze_suspend(server={"name": "server_name"},
                                  os_family="other_os")

        # with poweredon vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.Suspend = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOn"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.freeze_suspend(server={"name": "server_name"},
                                  os_family="other_os")
        vm.obj.Suspend.assert_called_with()

    @mock.patch("vsphere_plugin_common.SmartConnectNoSSL")
    @mock.patch('vsphere_plugin_common.Disconnect', mock.Mock())
    def test_freeze_resume(self, smart_m):
        conn_mock = mock.Mock()
        smart_m.return_value = conn_mock
        ctx = self._gen_ctx()

        # resume external resorce
        ctx.instance.runtime_properties['use_external_resource'] = True
        server.freeze_resume(server={"name": "server_name"},
                             os_family="other_os")

        # nosuch vm
        ctx.instance.runtime_properties['use_external_resource'] = False
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=None)
        ):
            with self.assertRaisesRegexp(
                NonRecoverableError,
                "Cannot resume server - server doesn't exist for node: "
                "node_name"
            ):
                server.freeze_resume(server={"name": "server_name"},
                                     os_family="other_os")

        # with started vm
        vm = mock.Mock()
        vm.obj.summary.runtime.powerState = "Poweredon"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.freeze_resume(server={"name": "server_name"},
                                 os_family="other_os")

        # with poweredoff vm
        vm = mock.Mock()
        task = mock.Mock()
        task.info.state = vim.TaskInfo.State.success
        vm.obj.snapshot = None  # no snapshots
        vm.obj.PowerOn = mock.Mock(return_value=task)
        vm.obj.summary.runtime.powerState = "PoweredOff"
        with mock.patch(
            "vsphere_plugin_common.VsphereClient._get_obj_by_name",
            mock.Mock(return_value=vm)
        ):
            server.freeze_resume(server={"name": "server_name"},
                                 os_family="other_os")
        vm.obj.PowerOn.assert_called_with()


if __name__ == '__main__':
    unittest.main()
