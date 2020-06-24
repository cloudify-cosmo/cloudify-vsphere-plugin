# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
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

from mock import Mock

from pyVmomi import vim

from cloudify.state import current_ctx
from cloudify.exceptions import NonRecoverableError

import vsphere_plugin_common


class NetworkClientTest(unittest.TestCase):

    def setUp(self):
        super(NetworkClientTest, self).setUp()
        self.mock_ctx = Mock()
        self.mock_ctx.instance.runtime_properties = {}
        current_ctx.set(self.mock_ctx)

    def test_delete_ippool(self):
        client = vsphere_plugin_common.NetworkClient()
        datacenter = Mock()
        client._get_obj_by_name = Mock(return_value=datacenter)
        client.si = Mock()
        # check delete code
        client.delete_ippool("datacenter", 123)
        # checks
        client._get_obj_by_name.assert_called_once_with(
            vsphere_plugin_common.clients.vim.Datacenter, "datacenter")
        client.si.content.ipPoolManager.DestroyIpPool.assert_called_once_with(
            dc=datacenter.obj, force=True, id=123)

        # no such datacenter
        client._get_obj_by_name = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.delete_ippool("datacenter", 123)

    def test_create_ippool(self):
        client = vsphere_plugin_common.NetworkClient()
        # no such datacenter
        client._get_obj_by_name = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.create_ippool("datacenter", {}, [])
        # create distribute
        datacenter = Mock()
        network = Mock()
        network.obj = vim.Network(Mock())
        results = [
            network,
            datacenter
        ]

        def _get_obj_by_name(_type, _name):
            return results.pop()

        client._get_obj_by_name = _get_obj_by_name
        network_instance = Mock()
        network_instance.runtime_properties = {
            "network_name": "some",
            "switch_distributed": True
        }
        client.si = Mock()
        client.si.content.ipPoolManager.CreateIpPool = Mock(return_value=124)
        self.assertEqual(
            client.create_ippool("datacenter", {
                "name": "ippool-check",
                "subnet": "192.0.2.0",
                "netmask": "255.255.255.0",
                "gateway": "192.0.2.254",
                "range": "192.0.2.1#12"
            }, [network_instance]),
            124)
        # legacy network
        client._get_obj_by_name = Mock(return_value=datacenter)
        client._collect_properties = Mock(
            return_value=[{"obj": vim.Network("network_id"),
                           "name": "some"}])
        network_instance = Mock()
        network_instance.runtime_properties = {
            "network_name": "some",
            "switch_distributed": False
        }
        client.si = Mock()
        client.si.content.ipPoolManager.CreateIpPool = Mock(return_value=124)
        self.assertEqual(
            client.create_ippool("datacenter", {
                "name": "ippool-check",
                "subnet": "192.0.2.0",
                "netmask": "255.255.255.0",
                "gateway": "192.0.2.254",
                "range": "192.0.2.1#12"
            }, [network_instance]),
            124)
        client._collect_properties.assert_called_once_with(
            vim.Network, path_set=['name'])

    def test_get_network_mtu(self):
        client = vsphere_plugin_common.NetworkClient()
        # distributed
        # no such network
        client._get_obj_by_name = Mock(return_value=None)
        with self.assertRaises(NonRecoverableError):
            client.get_network_mtu("some", True)
        # switch with mtu
        network = Mock()
        network.config.distributedVirtualSwitch.obj.config.maxMtu = 1234
        client._get_obj_by_name = Mock(return_value=network)
        self.assertEqual(client.get_network_mtu("some", True), 1234)
        # legacy
        client.get_host_list = Mock(return_value=[])
        self.assertEqual(client.get_network_mtu("some", False), -1)
        host1 = Mock()
        host2 = Mock()
        client.get_host_list = Mock(return_value=[host1, host2])
        switch1 = Mock()
        switch1.mtu = 1500
        switch1.portgroup = ["key-vim.host.PortGroup-some"]
        switch2 = Mock()
        switch2.mtu = 999
        switch2.portgroup = ["key-vim.host.PortGroup-some"]
        host1.config.network.vswitch = [switch1]
        host2.config.network.vswitch = [switch2]
        self.assertEqual(client.get_network_mtu("some", False), 999)

    def test_get_vswitch_mtu(self):
        client = vsphere_plugin_common.NetworkClient()
        client._get_hosts = Mock(return_value=[])
        self.assertEqual(client.get_vswitch_mtu("some"), -1)
        host1 = Mock()
        host2 = Mock()
        client._get_hosts = Mock(return_value=[host1, host2])
        switch1 = Mock()
        switch1.name = "some"
        switch1.mtu = 1500
        switch1.portgroup = ["key-vim.host.PortGroup-some"]
        switch2 = Mock()
        switch2.name = "some"
        switch2.mtu = 999
        switch2.portgroup = ["key-vim.host.PortGroup-some"]
        host1.config.network.vswitch = [switch1]
        host2.config.network.vswitch = [switch2]
        self.assertEqual(client.get_vswitch_mtu("some"), 999)

    def test_get_network_cidr(self):
        # no datacenters/ippools
        client = vsphere_plugin_common.NetworkClient()
        client.si = Mock()
        client.si.content.rootFolder.childEntity = []
        self.assertEqual(client.get_network_cidr("some", True), "0.0.0.0/0")
        # datacenter/ippool
        network = vim.dvs.DistributedVirtualPortgroup("check")
        datacenter = Mock()
        client.si.content.rootFolder.childEntity = [datacenter]
        pool = vim.vApp.IpPool(name='name')
        pool.ipv4Config = vim.vApp.IpPool.IpPoolConfigInfo()
        pool.ipv4Config.subnetAddress = "192.0.2.4"
        pool.ipv4Config.netmask = "255.255.255.0"
        pool.networkAssociation.insert(
            0,
            vim.vApp.IpPool.Association(network=network, networkName="some"))
        client.si.content.ipPoolManager.QueryIpPools = Mock(
            return_value=[pool])
        self.assertEqual(client.get_network_cidr("some", True), "192.0.2.4/24")
        client.si.content.ipPoolManager.QueryIpPools.assert_called_once_with(
            dc=datacenter)

    def test_delete_dv_port_group(self):
        client = vsphere_plugin_common.NetworkClient()
        task = Mock()
        task.info.state = vim.TaskInfo.State.success
        network = Mock()
        network.obj.Destroy = Mock(return_value=task)
        client._get_obj_by_name = Mock(return_value=network)
        client.delete_dv_port_group("abc", instance=self.mock_ctx.instance)
        client._get_obj_by_name.assert_called_once_with(
            vim.dvs.DistributedVirtualPortgroup, 'abc')
        network.obj.Destroy.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
