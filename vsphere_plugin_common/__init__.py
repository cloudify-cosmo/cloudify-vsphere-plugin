__author__ = 'Oleksandr_Raskosov'


from functools import wraps
import json
import os
import time
import unittest
import logging
import random
import string

from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import atexit

import cloudify.manager
import cloudify.decorators


TASK_CHECK_SLEEP = 15

PREFIX_RANDOM_CHARS = 3


class Config(object):
    def get(self):
        which = self.__class__.which
        env_name = which.upper() + '_CONFIG_PATH'
        default_location_tpl = '~/' + which + '_config.json'
        default_location = os.path.expanduser(default_location_tpl)
        config_path = os.getenv(env_name, default_location)
        try:
            with open(config_path) as f:
                cfg = json.loads(f.read())
        except IOError:
            raise RuntimeError(
                "Failed to read {0} configuration from file '{1}'."
                "The configuration is looked up in {2}. If defined, "
                "environment variable "
                "{3} overrides that location.".format(
                    which, config_path, default_location_tpl, env_name))
        return cfg


class ConnectionConfig(Config):
    which = 'connection'


class TestsConfig(Config):
    which = 'unit_tests'


class VsphereClient(object):

    config = ConnectionConfig

    def get(self, config=None, *args, **kw):
        static_config = self.__class__.config().get()
        cfg = {}
        cfg.update(static_config)
        if config:
            cfg.update(config)
        ret = self.connect(cfg)
        ret.format = 'json'
        return ret

    def connect(self, cfg):
        url = cfg['url']
        username = cfg['username']
        password = cfg['password']
        port = cfg['port']
        try:
            self.si = SmartConnect(host=url,
                                   user=username,
                                   pwd=password,
                                   port=int(port))
            atexit.register(Disconnect, self.si)
            return self
        except IOError as e:
            raise RuntimeError('config file validation error found'
                               ' during trying to connect: url:{0}. {1}'
                               .format(url, e.message))
        except vim.fault.InvalidLogin as e:
            raise RuntimeError('config file validation error found:'
                               ' could not connect to the specified url'
                               ' using specified username and password:'
                               ' url:{0}, username:{1}. {2}.'
                               .format(url, username, e.message))

    def _get_content(self):
        if "content" not in locals():
            self.content = self.si.RetrieveContent()
        return self.content

    def get_obj_list(self, vimtype):
        content = self._get_content()
        container_view = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        objects = container_view.view
        container_view.Destroy()
        return objects

    def _get_obj_by_name(self, vimtype, name, parent_name=None):
        obj = None
        objects = self.get_obj_list(vimtype)
        for c in objects:
            if c.name.lower() == name.lower()\
                    and (parent_name is None
                         or c.parent.name.lower() == parent_name.lower()):
                obj = c
                break
        return obj

    def _get_obj_by_id(self, vimtype, id, parent_name=None):
        obj = None
        content = self._get_content()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        for c in container.view:
            if c._moId == id \
                    and (parent_name is None
                         or c.parent.name.lower() == parent_name.lower()):
                obj = c
                break
        return obj

    def _wait_for_task(self, task):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(TASK_CHECK_SLEEP)
        if not task.info.state == vim.TaskInfo.State.success:
            raise task.info.error  # TODO


class ServerClient(VsphereClient):

    def create_server(self,
                      auto_placement,
                      cpus,
                      datacenter_name,
                      memory,
                      networks,
                      resource_pool_name,
                      template_name,
                      vm_name):
        host, datastore = self.place_vm(auto_placement)
        devices = []
        datacenter = self._get_obj_by_name([vim.Datacenter],
                                           datacenter_name)
        destfolder = datacenter.vmFolder
        resource_pool = self._get_obj_by_name([vim.ResourcePool],
                                              resource_pool_name,
                                              host.name)
        template_vm = self._get_obj_by_name([vim.VirtualMachine],
                                            template_name)
        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore
        relospec.pool = resource_pool
        if not auto_placement:
            relospec.host = host
        nicspec = vim.vm.device.VirtualDeviceSpec()
        for device in template_vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualVmxnet3):
                nicspec.device = device
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.remove
                devices.append(nicspec)
        for network in networks:
            network_name = network['name']
            network = self._get_obj_by_name([vim.Network], network_name)
            nicspec = vim.vm.device.VirtualDeviceSpec()
            nicspec.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.add
            nicspec.device = vim.vm.device.VirtualVmxnet3()
            nicspec.device.backing = \
                vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nicspec.device.backing.network = network
            nicspec.device.backing.deviceName = network_name
            devices.append(nicspec)

        # VM config spec
        vmconf = vim.vm.ConfigSpec()
        vmconf.numCPUs = cpus
        vmconf.memoryMB = memory
        vmconf.cpuHotAddEnabled = True
        vmconf.memoryHotAddEnabled = True
        vmconf.deviceChange = devices
        # Clone spec
        clonespec = vim.vm.CloneSpec()
        clonespec.location = relospec
        clonespec.config = vmconf
        clonespec.powerOn = True
        clonespec.template = False
        # fire the clone task
        task = template_vm.Clone(folder=destfolder,
                                 name=vm_name,
                                 spec=clonespec)
        try:
            self._wait_vm_running(task)
        except task.info.error:
            raise RuntimeError()  # TODO
        return task.info.result

    def start_server(self, server):
        task = server.PowerOn()
        self._wait_for_task(task)

    def shutdown_server_guest(self, server):
        server.ShutdownGuest()

    def stop_server(self, server):
        task = server.PowerOff()
        self._wait_for_task(task)

    def is_server_poweredoff(self, server):
        return server.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.guest.guestState == "running"

    def delete_server(self, server):
        if self.is_server_poweredon(server):
            task = server.PowerOff()
            self._wait_for_task(task)
        task = server.Destroy()
        self._wait_for_task(task)

    def get_server_by_name(self, name):
        return self._get_obj_by_name([vim.VirtualMachine], name)

    def get_server_by_id(self, id):
        return self._get_obj_by_id([vim.VirtualMachine], id)

    def get_server_list(self):
        return self.get_obj_list([vim.VirtualMachine])

    def place_vm(self, auto_placement):
        selected_datastore = None
        selected_host = None
        selected_host_memory = 0
        selected_host_memory_used = 0
        datastore_list = self.get_obj_list([vim.Datastore])
        for datastore in datastore_list:
            if selected_datastore is None:
                selected_datastore = datastore
            elif datastore.info.freeSpace > selected_datastore.info.freeSpace:
                selected_datastore = datastore

        if auto_placement:
            return None, selected_datastore

        for host_mount in selected_datastore.host:
            host = host_mount.key
            if selected_host is None:
                selected_host = host
            else:
                host_memory = host.hardware.memorySize
                host_memory_used = 0
                for vm in host.vm:
                    if not vm.summary.config.template:
                        host_memory_used += vm.summary.config.memorySizeMb

                host_memory_delta = host_memory - host_memory_used
                selected_host_memory_delta =\
                    selected_host_memory - selected_host_memory_used
                if host_memory_delta > selected_host_memory_delta:
                    selected_host = host
                    selected_host_memory = host_memory
                    selected_host_memory_used = host_memory_used
        return selected_host, selected_datastore

    def _wait_vm_running(self, task):
        self._wait_for_task(task)
        while not task.info.result.guest.guestState == "running"\
                or not task.info.result.guest.net:
            time.sleep(TASK_CHECK_SLEEP)


class NetworkClient(VsphereClient):

    def get_host_list(self):
        return self.get_obj_list([vim.HostSystem])

    def delete_port_group(self, name):
        host_list = self.get_host_list()
        for host in host_list:
            network_system = host.configManager.networkSystem
            network_system.RemovePortGroup(name)

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        host_list = self.get_host_list()
        for host in host_list:
            network_system = host.configManager.networkSystem

            specification = vim.host.PortGroup.Specification()
            specification.name = port_group_name
            specification.vlanId = vlan_id
            specification.vswitchName = vswitch_name
            vswitch = network_system.networkConfig.vswitch[0]
            specification.policy = vswitch.spec.policy
            network_system.AddPortGroup(specification)

    def get_port_group_by_name(self, name):
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    result.append(port_group)
        return result


def _find_instanceof_in_kw(cls, kw):
    ret = [v for v in kw.values() if isinstance(v, cls)]
    if not ret:
        return None
    if len(ret) > 1:
        raise RuntimeError(
            "Expected to find exactly one instance of {0} in "
            "kwargs but found {1}".format(cls, len(ret)))
    return ret[0]


def _find_context_in_kw(kw):
    return _find_instanceof_in_kw(cloudify.context.CloudifyContext, kw)


def with_server_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        ctx = _find_context_in_kw(kw)
        if ctx:
            config = ctx.properties.get('connection_config')
        else:
            config = None
        server_client = ServerClient().get(config=config)
        kw['server_client'] = server_client
        return f(*args, **kw)
    return wrapper


def with_network_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        ctx = _find_context_in_kw(kw)
        if ctx:
            config = ctx.properties.get('connection_config')
        else:
            config = None
        network_client = NetworkClient().get(config=config)
        kw['network_client'] = network_client
        return f(*args, **kw)
    return wrapper


class TestCase(unittest.TestCase):

    def get_server_client(self):
        r = ServerClient().get()
        self.get_server_client = lambda: r
        return self.get_server_client()

    def get_network_client(self):
        r = NetworkClient().get()
        self.get_network_client = lambda: r
        return self.get_network_client()

    def setUp(self):
        logger = logging.getLogger(__name__)
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logger
        self.logger.level = logging.DEBUG
        self.logger.debug("VSphere provider test setUp() called")
        chars = string.ascii_uppercase + string.digits
        self.name_prefix = 'vsphere_test_{0}_'\
            .format(''.join(
                random.choice(chars) for x in range(PREFIX_RANDOM_CHARS)))
        self.timeout = 120

        self.logger.debug("VSphere provider test setUp() done")

    def tearDown(self):
        self.logger.debug("VSphere provider test tearDown() called")
        # Compute
        self.logger.debug("Check are there any server to delete")
        server_client = self.get_server_client()
        for server in server_client.get_server_list():
            server_name = server.name
            if server_name.startswith(self.name_prefix):
                self.logger.debug("Deleting server \"{0}\""
                                  .format(server_name))
                server_client.delete_server(server)
            self.logger.debug("Will not delete server \"{0}\""
                              .format(server_name))
        # Network
        self.logger.debug("Check are there any network to delete")
        network_client = self.get_network_client()
        hosts = network_client.get_host_list()
        for host in hosts:
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                port_group_name = port_group.spec.name
                if port_group_name.startswith(self.name_prefix):
                    self.logger.debug("Deleting Port Group \"{0}\""
                                      " on host \"{1}\""
                                      .format(port_group_name, host.name))
                    network_system.RemovePortGroup(port_group_name)
                self.logger.debug("Will not delete Port Group \"{0}\""
                                  " on host \"{1}\""
                                  .format(port_group_name, host.name))
        self.logger.debug("VSphere provider test tearDown() done")

    @with_network_client
    def assertThereIsNoNetwork(self, name, network_client):
        port_groups = network_client.get_port_group_by_name(name)
        self.assertEquals(0, len(port_groups))

    @with_network_client
    def assertThereIsOneAndGetMetaNetwork(self, name, network_client):
        port_groups = network_client.get_port_group_by_name(name)
        self.assertNotEqual(0, len(port_groups))
        group_name = port_groups[0].spec.name
        group_vlanId = port_groups[0].spec.vlanId
        for port_group in port_groups[1:]:
            self.assertEqual(group_name, port_group.spec.name)
            self.assertEqual(group_vlanId, port_group.spec.vlanId)
        return {'name': group_name, 'vlanId': group_vlanId}

    @with_network_client
    def create_network(self, name, vlan_id, vswitch_name, network_client):
        network_client.create_port_group(name, vlan_id, vswitch_name)

    @with_server_client
    def assertThereIsNoServer(self, name, server_client):
        server = server_client.get_server_by_name(name)
        self.assertIsNone(server)

    @with_server_client
    def assertThereIsOneServerAndGet(self, name, server_client):
        server = server_client.get_server_by_name(name)
        self.assertIsNotNone(server)
        return server

    @with_server_client
    def assertServerIsStarted(self, server, server_client):
        self.assertTrue(server_client.is_server_poweredon(server))

    @with_server_client
    def assertServerIsStopped(self, server, server_client):
        self.assertTrue(server_client.is_server_poweredoff(server))

    def assertServerGuestIsStopped(self, server):
        self.assertFalse(self.is_server_guest_running(server))

    @with_server_client
    def is_server_guest_running(self, server, server_client):
        return server_client.is_server_guest_running(server)

    @with_server_client
    def is_server_stopped(self, server, server_client):
        return server_client.is_server_poweredoff(server)
