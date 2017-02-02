#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from __future__ import division

# Stdlib imports
import os
import re
import time
import atexit
from copy import copy
from functools import wraps

# Third party imports
import yaml
from netaddr import IPNetwork
from pyVmomi import vim, vmodl
from pyVim.connect import SmartConnect, Disconnect

# Cloudify imports
from cloudify import ctx
from cloudify import exceptions as cfy_exc

# This package imports
from vsphere_plugin_common.constants import (
    NETWORKS,
    NETWORK_ID,
    TASK_CHECK_SLEEP,
)
from vsphere_plugin_common.vendored_collections import namedtuple


def prepare_for_log(inputs):
    result = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            value = prepare_for_log(value)

        if 'password' in key:
            value = '**********'

        result[key] = value
    return result


def get_ip_from_vsphere_nic_ips(nic):
    for ip in nic.ipAddress:
        if ip.startswith('169.254.') or ip.lower().startswith('fe80::'):
            # This is a locally assigned IPv4 or IPv6 address and thus we
            # will assume it is not routable
            ctx.logger.debug('Found locally assigned IP {ip}. '
                             'Skipping.'.format(ip=ip))
            continue
        else:
            return ip
    # No valid IP was found
    return None


def remove_runtime_properties(properties, context):
    for p in properties:
        if p in context.instance.runtime_properties:
            del context.instance.runtime_properties[p]


class Config(object):

    # Required during vsphere manager bootstrap
    CONNECTION_CONFIG_PATH_DEFAULT = '~/connection_config.yaml'

    def get(self):
        cfg = {}
        which = self.__class__.which
        env_name = which.upper() + '_CONFIG_PATH'
        default_location_tpl = '~/' + which + '_config.yaml'
        default_location = os.path.expanduser(default_location_tpl)
        config_path = os.getenv(env_name, default_location)
        try:
            with open(config_path) as f:
                cfg = yaml.load(f.read())
        except IOError:
            ctx.logger.warn("Unable to read %s "
                            "configuration file %s." %
                            (which, config_path))

        return cfg


class ConnectionConfig(Config):
    which = 'connection'


class TestsConfig(Config):
    which = 'unit_tests'


class _ContainerView(object):
    def __init__(self, obj_type, service_instance):
        self.si = service_instance
        self.obj_type = obj_type

    def __enter__(self):
        container = self.si.content.rootFolder
        self.view_ref = self.si.content.viewManager.CreateContainerView(
            container=container,
            type=self.obj_type,
            recursive=True,
        )
        return self.view_ref

    def __exit__(self, *args):
        self.view_ref.Destroy()


class VsphereClient(object):

    config = ConnectionConfig

    def __init__(self):
        self._cache = {}

    def get(self, config=None, *args, **kw):
        static_config = self.__class__.config().get()
        cfg = {}
        cfg.update(static_config)
        if config:
            cfg.update(config)
        ret = self.connect(cfg)
        ret.format = 'yaml'
        return ret

    def connect(self, cfg):
        host = cfg['host']
        username = cfg['username']
        password = cfg['password']
        port = cfg['port']
        try:
            self.si = SmartConnect(host=host,
                                   user=username,
                                   pwd=password,
                                   port=int(port))
            atexit.register(Disconnect, self.si)
            return self
        except vim.fault.InvalidLogin:
            raise cfy_exc.NonRecoverableError(
                "Could not login to vSphere on {host} with provided "
                "credentials".format(host=host)
            )

    def is_server_suspended(self, server):
        return server.summary.runtime.powerState.lower() == "suspended"

    def _convert_props_list_to_dict(self, props_list):
        the_dict = {}
        split_list = [
            item.split('.', 1) for item in props_list
        ]
        vals = [
            item[0] for item in split_list
            if len(item) == 1
        ]
        keys = [
            item for item in split_list
            if len(item) > 1
        ]
        the_dict['_values'] = vals
        for item in keys:
            key_name = item[0]
            sub_keys = item[1:]
            dict_entry = the_dict.get(key_name, {})
            update_dict = self._convert_props_list_to_dict(
                sub_keys
            )
            if '_values' in dict_entry.keys():
                update_dict['_values'].extend(dict_entry['_values'])
            dict_entry.update(update_dict)
            the_dict[key_name] = dict_entry
        return the_dict

    def _get_platform_sub_results(self, platform_results, target_key):
        sub_results = {}
        for key, value in platform_results.items():
            key_components = key.split('.', 1)
            if key_components[0] == target_key:
                sub_results[key_components[1]] = value
        return sub_results

    def _make_cached_object(self, obj_name, props_dict, platform_results,
                            root_object=True, other_entity_mappings=None,
                            use_cache=True):
        just_keys = props_dict.keys()
        # Discard the _values key if it is present
        if '_values' in just_keys:
            just_keys.remove('_values')
        object_keys = copy(just_keys)
        object_keys.extend(props_dict.get('_values', []))
        if root_object:
            object_keys.extend(['id', 'obj'])
        object_keys = set(object_keys)
        obj = namedtuple(
            obj_name,
            object_keys,
        )

        args = {}
        for key in props_dict.get('_values', []):
            args[key] = platform_results[key]
        if root_object:
            args['id'] = platform_results['obj']._moId
            args['obj'] = platform_results['obj']

        if root_object and other_entity_mappings:
            for map_type in ('static', 'dynamic', 'single'):
                mappings = other_entity_mappings.get(map_type, {})
                for mapping, other_entities in mappings.items():
                    if map_type == 'single':
                        mapped = None
                        map_id = args[mapping]._moId
                        for entity in other_entities:
                            if entity.id == map_id:
                                mapped = entity
                                break
                    else:
                        mapping_ids = [
                            map_obj._moId for map_obj in args[mapping]
                        ]

                        mapped = [
                            other_entity for other_entity in other_entities
                            if other_entity.id in mapping_ids
                        ]

                        if (
                            map_type == 'static' and
                            len(mapped) != len(args[mapping])
                        ):
                            mapped = None

                    if mapped is None:
                        return ctx.operation.retry(
                            'Platform {entity} configuration changed '
                            'while building {obj_name} cache.'.format(
                                entity=mapping,
                                obj_name=obj_name,
                            )
                        )

                    args[mapping] = mapped

        for key in just_keys:
            sub_object_name = '{name}_{sub}'.format(
                name=obj_name,
                sub=key,
            )
            args[key] = self._make_cached_object(
                obj_name=sub_object_name,
                props_dict=props_dict[key],
                platform_results=self._get_platform_sub_results(
                    platform_results=platform_results,
                    target_key=key,
                ),
                root_object=False,
            )

        result = obj(
            **args
        )

        return result

    def _get_entity(self, entity_name, props, vimtype, use_cache=True,
                    other_entity_mappings=None, skip_broken_objects=False):
        if entity_name in self._cache and use_cache:
            return self._cache[entity_name]

        platform_results = self._collect_properties(
            vimtype,
            path_set=props,
        )

        props_dict = self._convert_props_list_to_dict(props)

        results = []
        for result in platform_results:
            try:
                results.append(
                    self._make_cached_object(
                        obj_name=entity_name,
                        props_dict=props_dict,
                        platform_results=result,
                        other_entity_mappings=other_entity_mappings,
                        use_cache=use_cache,
                    )
                )
            except KeyError as err:
                if not skip_broken_objects:
                    raise cfy_exc.NonRecoverableError(
                        'Could not retrieve all details for {type} object. '
                        '{err} was missing.'.format(
                            type=entity_name,
                            err=str(err)
                        )
                    )

        self._cache[entity_name] = results

        return results

    def _build_resource_pool_object(self, base_pool_id, resource_pools):
        rp_object = namedtuple(
            'resource_pool',
            ['name', 'resourcePool', 'id', 'obj'],
        )

        this_pool = None
        for pool in resource_pools:
            if pool['obj']._moId == base_pool_id:
                this_pool = pool
                break
        if this_pool is None:
            return ctx.operation.retry(
                'Resource pools changed while getting resource pool details.'
            )

        base_object = rp_object(
            name=this_pool['name'],
            id=this_pool['obj']._moId,
            resourcePool=[],
            obj=this_pool['obj'],
        )

        for item in this_pool['resourcePool']:
            base_object.resourcePool.append(self._build_resource_pool_object(
                base_pool_id=item._moId,
                resource_pools=resource_pools,
            ))

        return base_object

    def _get_resource_pools(self, use_cache=True):
        if 'resource_pool' in self._cache and use_cache:
            return self._cache['resource_pool']

        properties = [
            'name',
            'resourcePool',
        ]

        results = self._collect_properties(
            vim.ResourcePool,
            path_set=properties,
        )

        resource_pools = []
        for item in results:
            resource_pools.append(self._build_resource_pool_object(
                base_pool_id=item['obj']._moId,
                resource_pools=results
            ))

        self._cache['resource_pool'] = resource_pools

        return resource_pools

    def _get_clusters(self, use_cache=True):
        properties = [
            'name',
            'resourcePool',
        ]

        return self._get_entity(
            entity_name='cluster',
            props=properties,
            vimtype=vim.ClusterComputeResource,
            use_cache=use_cache,
            other_entity_mappings={
                'single': {
                    'resourcePool': self._get_resource_pools(
                        use_cache=use_cache,
                    ),
                },
            },
        )

    def _get_datacenters(self, use_cache=True):
        properties = [
            'name',
            'vmFolder',
        ]

        return self._get_entity(
            entity_name='datacenter',
            props=properties,
            vimtype=vim.Datacenter,
            use_cache=use_cache,
        )

    def _get_datastores(self, use_cache=True):
        properties = [
            'name',
            'overallStatus',
            'summary.accessible',
            'summary.freeSpace',
        ]

        return self._get_entity(
            entity_name='datastore',
            props=properties,
            vimtype=vim.Datastore,
            use_cache=use_cache,
        )

    def _get_connected_network_name(self, network):
        name = None
        if network.get('from_relationship'):
            net_id = None
            found = False
            for relationship in ctx.instance.relationships:
                if relationship.target.node.name == network['name']:
                    props = relationship.target.instance.runtime_properties
                    net_id = props.get(NETWORK_ID)
                    found = True
                    break
            if not found:
                raise cfy_exc.NonRecoverableError(
                    'Could not find any relationships to a node called '
                    '"{name}", so {prop} could not be retrieved.'.format(
                        name=network['name'],
                        prop=NETWORK_ID,
                    )
                )
            elif net_id is None:
                raise cfy_exc.NonRecoverableError(
                    'Could not get a {prop} runtime property from '
                    'relationship to a node called "{name}".'.format(
                        name=network['name'],
                        prop=NETWORK_ID,
                    )
                )

            if isinstance(net_id, list):
                # We won't alert on switch_distributed mismatch here, as the
                # validation logic handles that

                # Standard port groups will have multiple IDs, but since we
                # use the name, just using the first one will give the right
                # name
                net_id = net_id[0]

            net = self._get_obj_by_id(
                vimtype=vim.Network,
                id=net_id,
            )

            if net is None:
                raise cfy_exc.NonRecoverableError(
                    'Could not get network given network ID: {id}'.format(
                        id=net_id,
                    )
                )
            name = net.name
        else:
            name = network['name']
        return name

    def _get_networks(self, use_cache=True):
        if 'network' in self._cache and use_cache:
            return self._cache['network']

        properties = [
            'name',
            'host',
        ]
        net_object = namedtuple(
            'network',
            ['name', 'id', 'host', 'obj'],
        )
        dvnet_object = namedtuple(
            'distributed_network',
            ['name', 'id', 'host', 'obj', 'key', 'config'],
        )
        host_stub = namedtuple(
            'host_stub',
            ['id'],
        )

        results = self._collect_properties(
            vim.Network,
            path_set=properties,
        )

        extra_dv_port_group_details = self._get_extra_dv_port_group_details(
            use_cache
        )

        networks = []
        for item in results:
            network = net_object(
                name=item['name'],
                id=item['obj']._moId,
                host=[host_stub(id=h._moId) for h in item['host']],
                obj=item['obj'],
            )

            if self._port_group_is_distributed(network):
                extras = extra_dv_port_group_details[item['obj']._moId]

                network = dvnet_object(
                    name=item['name'],
                    id=item['obj']._moId,
                    obj=item['obj'],
                    host=[host_stub(id=h._moId) for h in item['host']],
                    key=extras['key'],
                    config=extras['config'],
                )

            networks.append(network)

        self._cache['network'] = networks

        return networks

    def _get_dv_networks(self, use_cache=True):
        return [
            network for network in self._get_networks(use_cache)
            if self._port_group_is_distributed(network)
        ]

    def _get_standard_networks(self, use_cache=True):
        return [
            network for network in self._get_networks(use_cache)
            if not self._port_group_is_distributed(network)
        ]

    def _get_extra_dv_port_group_details(self, use_cache=True):
        if 'dv_pg_extra_detail' in self._cache and use_cache:
            return self._cache['dv_pg_extra_detail']

        properties = [
            'key',
            'config.distributedVirtualSwitch',
        ]

        config_object = namedtuple(
            'dv_port_group_config',
            ['distributedVirtualSwitch'],
        )

        results = self._collect_properties(
            vim.dvs.DistributedVirtualPortgroup,
            path_set=properties,
        )

        dvswitches = self._get_dvswitches(use_cache)

        extra_details = {}
        for item in results:
            dvswitch_id = item['config.distributedVirtualSwitch']._moId
            dvswitch = None
            for dvs in dvswitches:
                if dvswitch_id == dvs.id:
                    dvswitch = dvs
                    break
            if dvswitch is None:
                return ctx.operation.retry(
                    'DVswitches on platform changed while getting port '
                    'group details.'
                )

            extra_details[item['obj']._moId] = {
                'key': item['key'],
                'config': config_object(distributedVirtualSwitch=dvswitch),
            }

        self._cache['dv_pg_extra_detail'] = extra_details

        return extra_details

    def _get_dvswitches(self, use_cache=True):
        properties = [
            'name',
            'uuid',
        ]

        return self._get_entity(
            entity_name='dvswitch',
            props=properties,
            vimtype=vim.dvs.VmwareDistributedVirtualSwitch,
            use_cache=use_cache,
        )

    def _get_vms(self, use_cache=True, skip_broken_vms=True):
        properties = [
            'name',
            'summary',
            'config.hardware.device',
            'datastore',
            'guest.guestState',
            'guest.net',
            'network',
        ]

        return self._get_entity(
            entity_name='vm',
            props=properties,
            vimtype=vim.VirtualMachine,
            use_cache=use_cache,
            other_entity_mappings={
                'static': {
                    'network': self._get_networks(use_cache=use_cache),
                    'datastore': self._get_datastores(use_cache=use_cache),
                },
            },
            # VMs still being cloned won't return everything we need
            skip_broken_objects=skip_broken_vms,
        )

    def _get_computes(self, use_cache=True):
        properties = [
            'name',
            'resourcePool',
        ]

        return self._get_entity(
            entity_name='compute',
            props=properties,
            vimtype=vim.ComputeResource,
            use_cache=use_cache,
            other_entity_mappings={
                'single': {
                    'resourcePool': self._get_resource_pools(
                        use_cache=use_cache,
                    ),
                },
            },
        )

    def _get_hosts(self, use_cache=True):
        properties = [
            'name',
            'parent',
            'hardware.memorySize',
            'hardware.cpuInfo.numCpuThreads',
            'overallStatus',
            'network',
            'summary.runtime.connectionState',
            'vm',
            'datastore',
            'config.network.vswitch',
            'configManager',
        ]

        # A host's parent can be either a cluster or a compute, so we handle
        # both here.
        return self._get_entity(
            entity_name='host',
            props=properties,
            vimtype=vim.HostSystem,
            use_cache=use_cache,
            other_entity_mappings={
                'single': {
                    'parent': (self._get_clusters(use_cache=use_cache) +
                               self._get_computes(use_cache=use_cache)),
                },
                'dynamic': {
                    'vm': self._get_vms(use_cache=use_cache),
                    'network': self._get_networks(use_cache=use_cache),
                },
                'static': {
                    'datastore': self._get_datastores(use_cache=use_cache),
                },
            },
        )

    def _get_getter_method(self, vimtype):
        getter_method = {
            vim.VirtualMachine: self._get_vms,
            vim.ResourcePool: self._get_resource_pools,
            vim.ClusterComputeResource: self._get_clusters,
            vim.Datastore: self._get_datastores,
            vim.Datacenter: self._get_datacenters,
            vim.Network: self._get_networks,
            vim.dvs.VmwareDistributedVirtualSwitch: self._get_dvswitches,
            vim.DistributedVirtualSwitch: self._get_dvswitches,
            vim.HostSystem: self._get_hosts,
            vim.dvs.DistributedVirtualPortgroup: self._get_dv_networks,
        }.get(vimtype)
        if getter_method is None:
            raise cfy_exc.NonRecoverableError(
                'Cannot retrieve objects for {vimtype}'.format(
                    vimtype=vimtype,
                )
            )

        return getter_method

    def _collect_properties(self, obj_type, path_set=None):
        """
        Collect properties for managed objects from a view ref
        Check the vSphere API documentation for example on retrieving
        object properties:
            - http://goo.gl/erbFDz
        Args:
            si          (ServiceInstance): ServiceInstance connection
            view_ref (pyVmomi.vim.view.*):/ Starting point of inventory
                                            navigation
            obj_type      (pyVmomi.vim.*): Type of managed object
            path_set               (list): List of properties to retrieve
        Returns:
            A list of properties for the managed objects
        """
        with _ContainerView([obj_type], self.si) as view_ref:
            collector = self.si.content.propertyCollector

            # Create object specification to define the starting point of
            # inventory navigation
            obj_spec = vmodl.query.PropertyCollector.ObjectSpec()
            obj_spec.obj = view_ref
            obj_spec.skip = True

            # Create a traversal specification to identify the path for
            # collection
            traversal_spec = vmodl.query.PropertyCollector.TraversalSpec()
            traversal_spec.name = 'traverseEntities'
            traversal_spec.path = 'view'
            traversal_spec.skip = False
            traversal_spec.type = view_ref.__class__
            obj_spec.selectSet = [traversal_spec]

            # Identify the properties to the retrieved
            property_spec = vmodl.query.PropertyCollector.PropertySpec()
            property_spec.type = obj_type

            if not path_set:
                property_spec.all = True

            property_spec.pathSet = path_set

            # Add the object and property specification to the
            # property filter specification
            filter_spec = vmodl.query.PropertyCollector.FilterSpec()
            filter_spec.objectSet = [obj_spec]
            filter_spec.propSet = [property_spec]

            # Retrieve properties
            props = collector.RetrieveContents([filter_spec])

        data = []
        for obj in props:
            properties = {}
            for prop in obj.propSet:
                properties[prop.name] = prop.val

            properties['obj'] = obj.obj

            data.append(properties)

        return data

    def _get_obj_by_name(self, vimtype, name, use_cache=True):
        obj = None

        entities = self._get_getter_method(vimtype)(use_cache)

        for entity in entities:
            if name.lower() == entity.name.lower():
                obj = entity
                break

        return obj

    def _get_obj_by_id(self, vimtype, id, use_cache=True):
        obj = None

        entities = self._get_getter_method(vimtype)(use_cache)
        for entity in entities:
            if entity.id == id:
                obj = entity
                break
        return obj

    def _wait_for_task(self, task):
        while task.info.state in (
            vim.TaskInfo.State.queued,
            vim.TaskInfo.State.running,
        ):
            time.sleep(TASK_CHECK_SLEEP)
        if task.info.state != vim.TaskInfo.State.success:
            raise cfy_exc.NonRecoverableError(
                "Error during executing task on vSphere: '{0}'"
                .format(task.info.error))

    def _port_group_is_distributed(self, port_group):
        return port_group.id.startswith('dvportgroup')

    def get_vm_networks(self, vm):
        """
            Get details of every network interface on a VM.
            A list of dicts with the following network interface information
            will be returned:
            {
                'name': Name of the network,
                'distributed': True if the network is distributed, otherwise
                               False,
                'mac': The MAC address as provided by vsphere,
            }
        """
        nics = []
        ctx.logger.debug('Getting NIC list')
        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                nics.append(dev)

        ctx.logger.debug('Got NICs: {nics}'.format(nics=nics))
        networks = []
        for nic in nics:
            ctx.logger.debug('Checking details for NIC {nic}'.format(nic=nic))
            distributed = hasattr(nic.backing, 'port') and isinstance(
                nic.backing.port,
                vim.dvs.PortConnection,
            )

            network_name = None
            if distributed:
                mapping_id = nic.backing.port.portgroupKey
                ctx.logger.debug(
                    'Found NIC was on distributed port group with port group '
                    'key {key}'.format(key=mapping_id)
                )
                for network in vm.network:
                    if hasattr(network, 'key'):
                        ctx.logger.debug(
                            'Checking for match on network with key: '
                            '{key}'.format(key=network.key)
                        )
                        if mapping_id == network.key:
                            network_name = network.name
                            ctx.logger.debug(
                                'Found NIC was distributed and was on '
                                'network {network}'.format(
                                    network=network_name,
                                )
                            )
            else:
                # If not distributed, the port group name can be retrieved
                # directly
                network_name = nic.backing.deviceName
                ctx.logger.debug(
                    'Found NIC was on port group {network}'.format(
                        network=network_name,
                    )
                )

            if network_name is None:
                raise cfy_exc.NonRecoverableError(
                    'Could not get network name for device with MAC address '
                    '{mac} on VM {vm}'.format(mac=nic.macAddress, vm=vm.name)
                )

            networks.append({
                'name': network_name,
                'distributed': distributed,
                'mac': nic.macAddress,
            })

        return networks


class ServerClient(VsphereClient):

    def _get_port_group_names(self):
        all_port_groups = self._get_networks()

        port_groups = []
        distributed_port_groups = []

        for port_group in all_port_groups:
            if self._port_group_is_distributed(port_group):
                distributed_port_groups.append(port_group.name.lower())
            else:
                port_groups.append(port_group.name.lower())

        return port_groups, distributed_port_groups

    def _validate_allowed(self, thing_type, allowed_things, existing_things):
        """
            Validate that an allowed hosts, clusters, or datastores list is
            valid.
        """
        ctx.logger.debug(
            'Checking allowed {thing}s list.'.format(thing=thing_type)
        )
        not_things = set(allowed_things).difference(set(existing_things))
        if len(not_things) == len(allowed_things):
            return (
                'No allowed {thing}s exist. Allowed {thing}(s): {allow}. '
                'Existing {thing}(s): {exist}.'.format(
                    allow=', '.join(allowed_things),
                    exist=', '.join(existing_things),
                    thing=thing_type,
                )
            )
        elif len(not_things) > 0:
            ctx.logger.warn(
                'One or more specified allowed {thing}s do not exist: '
                '{not_things}'.format(
                    thing=thing_type,
                    not_things=', '.join(not_things),
                )
            )

    def _validate_inputs(self,
                         allowed_hosts,
                         allowed_clusters,
                         allowed_datastores,
                         template_name,
                         datacenter_name,
                         resource_pool_name,
                         networks,
                         vm_cpus,
                         vm_memory):
        """
            Make sure we can actually continue with the inputs given.
            If we can't, we want to report all of the issues t once.
        """
        ctx.logger.debug('Validating inputs for this platform.')
        issues = []

        hosts = self._get_hosts()
        host_names = [host.name for host in hosts]

        if allowed_hosts:
            error = self._validate_allowed('host', allowed_hosts, host_names)
            if error:
                issues.append(error)

        if allowed_clusters:
            cluster_list = self._get_clusters()
            cluster_names = [cluster.name for cluster in cluster_list]
            error = self._validate_allowed(
                'cluster',
                allowed_clusters,
                cluster_names,
            )
            if error:
                issues.append(error)

        if allowed_datastores:
            datastore_list = self._get_datastores()
            datastore_names = [datastore.name for datastore in datastore_list]
            error = self._validate_allowed(
                'datastore',
                allowed_datastores,
                datastore_names,
            )
            if error:
                issues.append(error)

        ctx.logger.debug('Checking template exists.')
        template_vm = self._get_obj_by_name(vim.VirtualMachine,
                                            template_name)
        if template_vm is None:
            issues.append("VM template {0} could not be found.".format(
                template_name
            ))

        ctx.logger.debug('Checking resource pool exists.')
        resource_pool = self._get_obj_by_name(
            vim.ResourcePool,
            resource_pool_name,
        )
        if resource_pool is None:
            issues.append("Resource pool {0} could not be found.".format(
                resource_pool_name,
            ))

        ctx.logger.debug('Checking datacenter exists.')
        datacenter = self._get_obj_by_name(vim.Datacenter,
                                           datacenter_name)
        if datacenter is None:
            issues.append("Datacenter {0} could not be found.".format(
                datacenter_name
            ))

        ctx.logger.debug(
            'Checking networks exist.'
        )
        port_groups, distributed_port_groups = self._get_port_group_names()
        for network in networks:
            try:
                network_name = self._get_connected_network_name(network)
            except cfy_exc.NonRecoverableError as err:
                issues.append(str(err))
                continue
            network_name_lower = network_name.lower()
            switch_distributed = network['switch_distributed']

            list_distributed_networks = False
            list_networks = False
            # Check network exists and provide helpful message if it doesn't
            # Note that we special-case alerting if switch_distributed appears
            # to be set incorrectly.
            # Use lowercase name for comparison as vSphere appears to be case
            # insensitive for this.
            if switch_distributed:
                error_message = (
                    'Distributed network "{name}" not present on vSphere.'
                )
                if network_name_lower not in distributed_port_groups:
                    if network_name_lower in port_groups:
                        issues.append(
                            (error_message + ' However, this is present as a '
                             'standard network. You may need to set the '
                             'switch_distributed setting for this network to '
                             'false.').format(name=network_name)
                        )
                    else:
                        issues.append(error_message.format(name=network_name))
                        list_distributed_networks = True
            else:
                error_message = 'Network "{name}" not present on vSphere.'
                if network_name_lower not in port_groups:
                    if network_name_lower in distributed_port_groups:
                        issues.append(
                            (error_message + ' However, this is present as a '
                             'distributed network. You may need to set the '
                             'switch_distributed setting for this network to '
                             'true.').format(name=network_name)
                        )
                    else:
                        issues.append(error_message.format(name=network_name))
                        list_networks = True

            if list_distributed_networks:
                issues.append(
                    (' Available distributed networks '
                     'are: {nets}.').format(
                        name=network_name,
                        nets=', '.join(distributed_port_groups),
                    )
                )
            if list_networks:
                issues.append(
                    (' Available networks are: '
                     '{nets}.').format(
                        name=network_name,
                        nets=', '.join(port_groups),
                    )
                )

        if vm_cpus < 1:
            issues.append('At least one vCPU must be assigned.')

        if vm_memory < 1:
            issues.append('Assigned memory cannot be less than 1MB.')

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise cfy_exc.NonRecoverableError(message)

    def _validate_windows_properties(self, props, password):
        issues = []

        props_password = props.get('windows_password')
        if props_password == '':
            # Avoid falsey comparison on blank password
            props_password = True
        if password == '':
            # Avoid falsey comparison on blank password
            password = True
        custom_sysprep = props.get('custom_sysprep')
        if custom_sysprep is not None:
            if props_password:
                issues.append(
                    'custom_sysprep answers data has been provided, but a '
                    'windows_password was supplied. If using custom sysprep, '
                    'no other windows settings are usable.'
                )
        elif not props_password and custom_sysprep is None:
            if not password:
                issues.append(
                    'Windows password must be set when a custom sysprep is '
                    'not being performed. Please supply a windows_password '
                    'using either properties.windows_password or '
                    'properties.agent_config.password'
                )

        if len(props['windows_organization']) == 0:
            issues.append('windows_organization property must not be blank')
        if len(props['windows_organization']) > 64:
            issues.append(
                'windows_organization property must be 64 characters or less')

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise cfy_exc.NonRecoverableError(message)

    def create_server(self,
                      auto_placement,
                      cpus,
                      datacenter_name,
                      memory,
                      networks,
                      resource_pool_name,
                      template_name,
                      vm_name,
                      os_type='linux',
                      domain=None,
                      dns_servers=None,
                      allowed_hosts=None,
                      allowed_clusters=None,
                      allowed_datastores=None):
        ctx.logger.debug("Entering create_server with parameters %s"
                         % prepare_for_log(locals()))

        self._validate_inputs(
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
            allowed_datastores=allowed_datastores,
            template_name=template_name,
            networks=networks,
            resource_pool_name=resource_pool_name,
            datacenter_name=datacenter_name,
            vm_cpus=cpus,
            vm_memory=memory,
        )

        # Correct the network name for all networks from relationships
        for network in networks:
            network['name'] = self._get_connected_network_name(network)

        candidate_hosts = self.find_candidate_hosts(
            resource_pool=resource_pool_name,
            vm_cpus=cpus,
            vm_memory=memory,
            vm_networks=networks,
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
        )

        template_vm = self._get_obj_by_name(vim.VirtualMachine,
                                            template_name)

        host, datastore = self.select_host_and_datastore(
            candidate_hosts=candidate_hosts,
            vm_memory=memory,
            template=template_vm,
            allowed_datastores=allowed_datastores,
        )
        ctx.logger.debug(
            'Using host {host} and datastore {ds} for deployment.'.format(
                host=host.name,
                ds=datastore.name,
            )
        )

        devices = []
        adaptermaps = []

        resource_pool = self.get_resource_pool(
            host=host,
            resource_pool_name=resource_pool_name,
        )

        datacenter = self._get_obj_by_name(vim.Datacenter,
                                           datacenter_name)

        destfolder = datacenter.vmFolder
        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore.obj
        relospec.pool = resource_pool.obj
        if not auto_placement:
            relospec.host = host.obj

        nicspec = vim.vm.device.VirtualDeviceSpec()
        for device in template_vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualVmxnet3):
                nicspec.device = device
                ctx.logger.warn('Removing network adapter from template. '
                                'Template should have no attached adapters.')
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.remove
                devices.append(nicspec)

        port_groups, distributed_port_groups = self._get_port_group_names()

        for network in networks:
            network_name = network['name']
            network_name_lower = network_name.lower()
            switch_distributed = network['switch_distributed']

            use_dhcp = network['use_dhcp']
            if switch_distributed:
                network_obj = self._get_obj_by_name(
                    vim.dvs.DistributedVirtualPortgroup,
                    network_name,
                )
            else:
                network_obj = self._get_obj_by_name(
                    vim.Network,
                    network_name,
                )
            if network_obj is None:
                raise cfy_exc.NonRecoverableError(
                    'Network {0} could not be found'.format(network_name))
            nicspec = vim.vm.device.VirtualDeviceSpec()
            # Info level as this is something that was requested in the
            # blueprint
            ctx.logger.info('Adding network interface on {name} to {server}'
                            .format(name=network_name,
                                    server=vm_name))
            nicspec.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.add
            nicspec.device = vim.vm.device.VirtualVmxnet3()
            if switch_distributed:
                info = vim.vm.device.VirtualEthernetCard\
                    .DistributedVirtualPortBackingInfo()
                nicspec.device.backing = info
                nicspec.device.backing.port =\
                    vim.dvs.PortConnection()
                nicspec.device.backing.port.switchUuid =\
                    network_obj.config.distributedVirtualSwitch.uuid
                nicspec.device.backing.port.portgroupKey =\
                    network_obj.key
            else:
                nicspec.device.backing = \
                    vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
                nicspec.device.backing.network = network_obj.obj
                nicspec.device.backing.deviceName = network_name
            devices.append(nicspec)

            if use_dhcp:
                guest_map = vim.vm.customization.AdapterMapping()
                guest_map.adapter = vim.vm.customization.IPSettings()
                guest_map.adapter.ip = vim.vm.customization.DhcpIpGenerator()
                adaptermaps.append(guest_map)
            else:
                nw = IPNetwork(network["network"])
                guest_map = vim.vm.customization.AdapterMapping()
                guest_map.adapter = vim.vm.customization.IPSettings()
                guest_map.adapter.ip = vim.vm.customization.FixedIp()
                guest_map.adapter.ip.ipAddress = network['ip']
                guest_map.adapter.gateway = network["gateway"]
                guest_map.adapter.subnetMask = str(nw.netmask)
                adaptermaps.append(guest_map)

        vmconf = vim.vm.ConfigSpec()
        vmconf.numCPUs = cpus
        vmconf.memoryMB = memory
        vmconf.cpuHotAddEnabled = True
        vmconf.memoryHotAddEnabled = True
        vmconf.cpuHotRemoveEnabled = True
        vmconf.deviceChange = devices

        clonespec = vim.vm.CloneSpec()
        clonespec.location = relospec
        clonespec.config = vmconf
        clonespec.powerOn = True
        clonespec.template = False

        if adaptermaps:
            ctx.logger.debug(
                'Preparing OS customization spec for {server}'.format(
                    server=vm_name,
                )
            )
            customspec = vim.vm.customization.Specification()
            customspec.nicSettingMap = adaptermaps

            if os_type is None or os_type == 'linux':
                ident = vim.vm.customization.LinuxPrep()
                if domain:
                    ident.domain = domain
                ident.hostName = vim.vm.customization.FixedName()
                ident.hostName.name = vm_name
            elif os_type == 'windows':
                props = ctx.node.properties
                password = props.get('windows_password')
                if not password:
                    agent_config = props.get('agent_config', {})
                    password = agent_config.get('password')

                self._validate_windows_properties(props, password)

                custom_sysprep = props.get('custom_sysprep')
                if custom_sysprep is not None:
                    ident = vim.vm.customization.SysprepText()
                    ident.value = custom_sysprep
                else:
                    # We use GMT without daylight savings if no timezone is
                    # supplied, as this is as close to UTC as we can do
                    timezone = props.get('windows_timezone', 90)

                    ident = vim.vm.customization.Sysprep()
                    ident.userData = vim.vm.customization.UserData()
                    ident.guiUnattended = vim.vm.customization.GuiUnattended()
                    ident.identification = (
                        vim.vm.customization.Identification()
                    )

                    # Configure userData
                    ident.userData.computerName = (
                        vim.vm.customization.FixedName()
                    )
                    ident.userData.computerName.name = vm_name
                    # Without these vars, customization is silently skipped
                    # but deployment 'succeeds'
                    ident.userData.fullName = vm_name
                    ident.userData.orgName = props.get('windows_organization')
                    ident.userData.productId = ""

                    # Configure guiUnattended
                    ident.guiUnattended.autoLogon = False
                    ident.guiUnattended.password = (
                        vim.vm.customization.Password()
                    )
                    ident.guiUnattended.password.plainText = True
                    ident.guiUnattended.password.value = password
                    ident.guiUnattended.timeZone = timezone

                # Adding windows options
                options = vim.vm.customization.WinOptions()
                options.changeSID = True
                options.deleteAccounts = False
                customspec.options = options
            else:
                raise cfy_exc.NonRecoverableError(
                    'os_type {os_type} was specified, but only "windows" and '
                    '"linux" are supported.'.format(os_type=os_type)
                )

            customspec.identity = ident

            globalip = vim.vm.customization.GlobalIPSettings()
            if dns_servers:
                globalip.dnsServerList = dns_servers
            customspec.globalIPSettings = globalip

            clonespec.customization = customspec
        ctx.logger.info('Cloning {server} from {template}.'
                        .format(server=vm_name, template=template_name))
        task = template_vm.obj.Clone(folder=destfolder,
                                     name=vm_name,
                                     spec=clonespec)
        try:
            ctx.logger.debug("Task info: \n%s." %
                             "".join("%s: %s" % item
                                     for item in vars(task).items()))
            self._wait_vm_running(task, adaptermaps)
        except task.info.error:
            raise cfy_exc.NonRecoverableError(
                "Error during executing VM creation task. VM name: \'{0}\'."
                .format(vm_name))

        vm = self._get_obj_by_name(
            vim.VirtualMachine,
            vm_name,
            use_cache=False,
        )
        ctx.instance.runtime_properties[NETWORKS] = \
            self.get_vm_networks(vm)
        ctx.logger.debug('Updated runtime properties with network information')

        return task.info.result

    def start_server(self, server):
        if self.is_server_poweredon(server):
            ctx.logger.info("Server '{}' already running".format(server.name))
            return
        ctx.logger.debug("Entering server start procedure.")
        task = server.obj.PowerOn()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now running.")

    def shutdown_server_guest(
        self, server,
        timeout=TASK_CHECK_SLEEP,
        max_wait_time=300,
    ):
        if self.is_server_poweredoff(server):
            ctx.logger.info("Server '{}' already stopped".format(server.name))
            return
        ctx.logger.debug("Entering server shutdown procedure.")
        server.obj.ShutdownGuest()
        for _ in range(max_wait_time // timeout):
            time.sleep(timeout)
            if self.is_server_poweredoff(server):
                break
        else:
            raise cfy_exc.NonRecoverableError(
                "Server still running after {time}s timeout.".format(
                    time=max_wait_time,
                ))
        ctx.logger.debug("Server is now shut down.")

    def stop_server(self, server):
        if self.is_server_poweredoff(server):
            ctx.logger.info("Server '{}' already stopped".format(server.name))
            return
        ctx.logger.debug("Entering stop server procedure.")
        task = server.obj.PowerOff()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now stopped.")

    def reset_server(self, server):
        if self.is_server_poweredoff(server):
            ctx.logger.info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server)
        ctx.logger.debug("Entering stop server procedure.")
        task = server.obj.Reset()
        self._wait_for_task(task)
        ctx.logger.debug("Server has been reset")

    def reboot_server(
        self, server,
        timeout=TASK_CHECK_SLEEP,
        max_wait_time=300,
    ):
        if self.is_server_poweredoff(server):
            ctx.logger.info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server)
        ctx.logger.debug("Entering reboot server procedure.")
        start_bootTime = server.obj.runtime.bootTime
        server.obj.RebootGuest()
        for _ in range(max_wait_time // timeout):
            time.sleep(timeout)
            if server.obj.runtime.bootTime > start_bootTime:
                break
        else:
            raise cfy_exc.NonRecoverableError(
                "Server still running after {time}s timeout.".format(
                    time=max_wait_time,
                ))
        ctx.logger.debug("Server has been rebooted")

    def is_server_poweredoff(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.obj.guest.guestState == "running"

    def delete_server(self, server):
        ctx.logger.debug("Entering server delete procedure.")
        if self.is_server_poweredon(server):
            self.stop_server(server)
        task = server.obj.Destroy()
        self._wait_for_task(task)
        ctx.logger.debug("Server is now deleted.")

    def get_server_by_name(self, name):
        return self._get_obj_by_name(vim.VirtualMachine, name)

    def get_server_by_id(self, id):
        return self._get_obj_by_id(vim.VirtualMachine, id)

    def find_candidate_hosts(self,
                             resource_pool,
                             vm_cpus,
                             vm_memory,
                             vm_networks,
                             allowed_hosts=None,
                             allowed_clusters=None):
        ctx.logger.debug('Finding suitable hosts for deployment.')

        hosts = self._get_hosts()
        host_names = [host.name for host in hosts]
        ctx.logger.debug(
            'Found hosts: {hosts}'.format(
                hosts=', '.join(host_names),
            )
        )

        if allowed_hosts:
            hosts = [host for host in hosts if host.name in allowed_hosts]
            ctx.logger.debug(
                'Filtered list of hosts to be considered: {hosts}'.format(
                    hosts=', '.join(host_names),
                )
            )

        if allowed_clusters:
            cluster_list = self._get_clusters()
            cluster_names = [cluster.name for cluster in cluster_list]
            valid_clusters = set(allowed_clusters).union(set(cluster_names))
            ctx.logger.debug(
                'Only hosts on the following clusters will be used: '
                '{clusters}'.format(
                    clusters=', '.join(valid_clusters),
                )
            )

        candidate_hosts = []
        for host in hosts:
            if not self.host_is_usable(host):
                ctx.logger.warn(
                    'Host {host} not usable due to health status.'.format(
                        host=host.name,
                    )
                )
                continue

            if allowed_clusters:
                cluster = self.get_host_cluster_membership(host)
                if cluster not in allowed_clusters:
                    if cluster:
                        ctx.logger.warn(
                            'Host {host} is in cluster {cluster}, '
                            'which is not an allowed cluster.'.format(
                                host=host.name,
                                cluster=cluster,
                            )
                        )
                    else:
                        ctx.logger.warn(
                            'Host {host} is not in a cluster, '
                            'and allowed clusters have been set.'.format(
                                host=host.name,
                            )
                        )
                    continue

            memory_weight = self.host_memory_usage_ratio(host, vm_memory)

            if memory_weight < 0:
                ctx.logger.warn(
                    'Host {host} will not have enough free memory if all VMs '
                    'are powered on.'.format(
                        host=host.name,
                    )
                )

            resource_pools = self.get_host_resource_pools(host)
            resource_pools = [pool.name for pool in resource_pools]
            if resource_pool not in resource_pools:
                ctx.logger.warn(
                    'Host {host} does not have resource pool {rp}.'.format(
                        host=host.name,
                        rp=resource_pool,
                    )
                )
                continue

            host_nets = set([
                (
                    network['name'],
                    network['switch_distributed'],
                )
                for network in self.get_host_networks(host)
            ])
            vm_nets = set([
                (
                    network['name'],
                    network['switch_distributed'],
                )
                for network in vm_networks
            ])

            nets_not_on_host = vm_nets.difference(host_nets)

            if nets_not_on_host:
                message = 'Host {host} does not have all required networks. '

                missing_standard_nets = ', '.join([
                    net[0] for net in nets_not_on_host
                    if not net[1]
                ])
                missing_distributed_nets = ', '.join([
                    net[0] for net in nets_not_on_host
                    if net[1]
                ])

                if missing_standard_nets:
                    message += 'Missing standard networks: {nets}. '

                if missing_distributed_nets:
                    message += 'Missing distributed networks: {dnets}. '

                ctx.logger.warn(
                    message.format(
                        host=host.name,
                        nets=missing_standard_nets,
                        dnets=missing_distributed_nets,
                    )
                )
                continue

            ctx.logger.debug(
                'Host {host} is a candidate for deployment.'.format(
                    host=host.name,
                )
            )
            candidate_hosts.append((
                host,
                self.host_cpu_thread_usage_ratio(host, vm_cpus),
                memory_weight,
            ))

        # Sort hosts based on the best processor ratio after deployment
        if candidate_hosts:
            ctx.logger.debug(
                'Host CPU ratios: {ratios}'.format(
                    ratios=', '.join([
                        '{hostname}: {ratio} {mem_ratio}'.format(
                            hostname=c[0].name,
                            ratio=c[1],
                            mem_ratio=c[2],
                        ) for c in candidate_hosts
                    ])
                )
            )
        candidate_hosts.sort(
            reverse=True,
            key=lambda host_rating: host_rating[1] * host_rating[2]
            # If more ratios are added, take care that they are proper ratios
            # (i.e. > 0), because memory ([2]) isn't, and 2 negatives would
            # cause badly ordered candidates.
        )

        if candidate_hosts:
            return candidate_hosts
        else:
            message = (
                "No healthy hosts could be found with resource pool {pool}, "
                "and all required networks."
            ).format(pool=resource_pool, memory=vm_memory)

            if allowed_hosts:
                message += " Only these hosts were allowed: {hosts}".format(
                    hosts=', '.join(allowed_hosts)
                )
            if allowed_clusters:
                message += (
                    " Only hosts in these clusters were allowed: {clusters}"
                ).format(
                    clusters=', '.join(allowed_clusters)
                )

            raise cfy_exc.NonRecoverableError(message)

    def get_resource_pool(self, host, resource_pool_name):
        """
            Get the correct resource pool object from the given host.
        """
        resource_pools = self.get_host_resource_pools(host)
        for resource_pool in resource_pools:
            if resource_pool.name == resource_pool_name:
                return resource_pool
        # If we get here, we somehow selected a host without the right
        # resource pool. This should not be able to happen.
        raise cfy_exc.NonRecoverableError(
            'Resource pool {rp} not found on host {host}. '
            'Pools found were: {pools}'.format(
                rp=resource_pool_name,
                host=host.name,
                pools=', '.join([p.name for p in resource_pools]),
            )
        )

    def select_host_and_datastore(self,
                                  candidate_hosts,
                                  vm_memory,
                                  template,
                                  allowed_datastores=None):
        """
            Select which host and datastore to use.
            This will assume that the hosts are sorted from most desirable to
            least desirable.
        """
        ctx.logger.debug('Selecting best host and datastore.')

        best_host = None
        best_datastore = None
        best_datastore_weighting = None

        if allowed_datastores:
            datastore_list = self._get_datastores()
            datastore_names = [datastore.name for datastore in datastore_list]

            valid_datastores = set(allowed_datastores).union(
                set(datastore_names)
            )
            ctx.logger.debug(
                'Only the following datastores will be used: '
                '{datastores}'.format(
                    datastores=', '.join(valid_datastores),
                )
            )

        for host in candidate_hosts:
            host = host[0]
            ctx.logger.debug('Considering host {host}'.format(host=host.name))

            datastores = host.datastore
            ctx.logger.debug(
                'Host {host} has datastores: {ds}'.format(
                    host=host.name,
                    ds=', '.join([ds.name for ds in datastores]),
                )
            )
            if allowed_datastores:
                ctx.logger.debug(
                    'Checking only allowed datastores: {allow}'.format(
                        allow=', '.join(allowed_datastores),
                    )
                )

                datastores = [
                    ds for ds in datastores
                    if ds.name in allowed_datastores
                ]

                if len(datastores) == 0:
                    ctx.logger.warn(
                        'Host {host} had no allowed datastores.'.format(
                            host=host.name,
                        )
                    )
                    continue

            ctx.logger.debug(
                'Filtering for healthy datastores on host {host}'.format(
                    host=host.name,
                )
            )

            healthy_datastores = []
            for datastore in datastores:
                if self.datastore_is_usable(datastore):
                    ctx.logger.debug(
                        'Datastore {ds} on host {host} is healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )
                    healthy_datastores.append(datastore)
                else:
                    ctx.logger.warn(
                        'Excluding datastore {ds} on host {host} as it is '
                        'not healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )

            if len(healthy_datastores) == 0:
                ctx.logger.warn(
                    'Host {host} has no usable datastores.'.format(
                        host=host.name,
                    )
                )

            candidate_datastores = []
            for datastore in healthy_datastores:
                weighting = self.calculate_datastore_weighting(
                    datastore=datastore,
                    vm_memory=vm_memory,
                    template=template,
                )
                if weighting is not None:
                    ctx.logger.debug(
                        'Datastore {ds} on host {host} has suitability '
                        '{weight}'.format(
                            ds=datastore.name,
                            weight=weighting,
                            host=host.name,
                        )
                    )
                    candidate_datastores.append((datastore, weighting))
                else:
                    ctx.logger.warn(
                        'Datastore {ds} on host {host} does not have enough '
                        'free space.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )

            if candidate_datastores:
                candidate_host = host
                candidate_datastore, candidate_datastore_weighting = max(
                    candidate_datastores,
                    key=lambda datastore: datastore[1],
                )

                if best_datastore is None:
                    best_host = candidate_host
                    best_datastore = candidate_datastore
                    best_datastore_weighting = candidate_datastore_weighting
                else:
                    if best_datastore_weighting < 0:
                        # Use the most desirable host unless it can't house
                        # the VM's maximum space usage (assuming the entire
                        # virtual disk is filled up), and unless this
                        # datastore can.
                        if candidate_datastore_weighting >= 0:
                            best_host = candidate_host
                            best_datastore = candidate_datastore
                            best_datastore_weighting = (
                                candidate_datastore_weighting
                            )

                if candidate_host == best_host and (
                    candidate_datastore == best_datastore
                ):
                    ctx.logger.debug(
                        'Host {host} and datastore {datastore} are current '
                        'best candidate. Best datastore weighting '
                        '{weight}.'.format(
                            host=best_host.name,
                            datastore=best_datastore.name,
                            weight=best_datastore_weighting,
                        )
                    )

        if best_host is not None:
            return best_host, best_datastore
        else:
            message = 'No datastores found with enough space.'
            if allowed_datastores:
                message += ' Only these datastores were allowed: {ds}'
                message = message.format(ds=', '.join(allowed_datastores))
            message += ' Only the suitable candidate hosts were checked: '
            message += '{hosts}'.format(hosts=', '.join(
                [hostt[0].name for hostt in candidate_hosts]
            ))
            raise cfy_exc.NonRecoverableError(message)

    def get_host_free_memory(self, host):
        """
            Get the amount of unallocated memory on a host.
        """
        total_memory = host.hardware.memorySize // 1024 // 1024
        used_memory = 0
        for vm in host.vm:
            if not vm.summary.config.template:
                used_memory += vm.summary.config.memorySizeMB
        return total_memory - used_memory

    def host_cpu_thread_usage_ratio(self, host, vm_cpus):
        """
            Check the usage ratio of actual CPU threads to assigned threads.
            This should give a higher rating to those hosts with less threads
            assigned compared to their total available CPU threads.

            This is used rather than a simple absolute number of cores
            remaining to avoid allocating to a less sensible host if, for
            example, there are two hypervisors, one with 12 CPU threads and
            one with 6, both of which have 4 more virtual CPUs assigned than
            actual CPU threads. In this case, both would be rated at -4, but
            the actual impact on the one with 12 threads would be lower.
        """
        total_threads = host.hardware.cpuInfo.numCpuThreads

        total_assigned = vm_cpus
        for vm in host.vm:
            total_assigned += vm.summary.config.numCpu

        return total_threads / total_assigned

    def host_memory_usage_ratio(self, host, new_mem):
        """
        Return the proporiton of resulting memory overcommit if a VM with
        new_mem is added to this host.
        """
        free_memory = self.get_host_free_memory(host)
        free_memory_after = free_memory - new_mem
        weight = free_memory_after / (host.hardware.memorySize // 1024 // 1024)

        return weight

    def datastore_is_usable(self, datastore):
        """
            Return True if this datastore is usable for deployments,
            based on its health.
            Return False otherwise.
        """
        return datastore.overallStatus in (
            vim.ManagedEntity.Status.green,
            vim.ManagedEntity.Status.yellow,
        ) and datastore.summary.accessible

    def calculate_datastore_weighting(self,
                                      datastore,
                                      vm_memory,
                                      template):
        """
            Determine how suitable this datastore is for this deployment.
            Returns None if it is not suitable. Otherwise, returns a weighting
            where higher is better.
        """
        # We assign memory in MB, but free space is in B
        vm_memory = vm_memory * 1024 * 1024

        free_space = datastore.summary.freeSpace
        minimum_disk = template.summary.storage.committed
        maximum_disk = template.summary.storage.uncommitted

        minimum_used = minimum_disk + vm_memory
        maximum_used = minimum_used + maximum_disk

        if free_space - minimum_used < 0:
            return None
        else:
            return free_space - maximum_used

    def recurse_resource_pools(self, resource_pool):
        """
            Recursively get all child resource pools given a resource pool.
            Return a list of all resource pools found.
        """
        resource_pool_names = []
        for pool in resource_pool.resourcePool:
            resource_pool_names.append(pool)
            resource_pool_names.extend(self.recurse_resource_pools(pool))
        return resource_pool_names

    def get_host_networks(self, host):
        """
            Get all networks attached to this host.
            Returns a list of dicts in the form:
            {
                'name': <name of network>,
                'switch_distributed': <whether net is distributed>,
            }
        """
        nets = [
            {
                'name': net.name,
                'switch_distributed': self._port_group_is_distributed(net),
            }
            for net in host.network
        ]
        return nets

    def get_host_resource_pools(self, host):
        """
            Get all resource pools available on this host.
            This will work for hosts inside and outside clusters.
            A list of resource pools will be returned, e.g.
            ['Resources', 'myresourcepool', 'anotherone']
        """
        base_resource_pool = host.parent.resourcePool
        resource_pools = [base_resource_pool]
        child_resource_pools = self.recurse_resource_pools(base_resource_pool)
        resource_pools.extend(child_resource_pools)
        return resource_pools

    def get_host_cluster_membership(self, host):
        """
            Return the name of the cluster this host is part of,
            or None if it is not part of a cluster.
        """
        if isinstance(host.parent, vim.ClusterComputeResource):
            return host.parent.name
        else:
            return None

    def host_is_usable(self, host):
        """
            Return True if this host is usable for deployments,
            based on its health.
            Return False otherwise.
        """
        if host.overallStatus in (
            vim.ManagedEntity.Status.green,
            vim.ManagedEntity.Status.yellow,
        ) and host.summary.runtime.connectionState == 'connected':
            # TODO: Check license state (will be yellow for bad license)
            return True
        else:
            return False

    def resize_server(self, server, cpus=None, memory=None):
        ctx.logger.debug("Entering resize reconfiguration.")
        config = vim.vm.ConfigSpec()
        if cpus is not None:
            try:
                cpus = int(cpus)
            except (ValueError, TypeError) as e:
                raise cfy_exc.NonRecoverableError(
                    "Invalid cpus value: {}".format(e))
            if cpus < 1:
                raise cfy_exc.NonRecoverableError(
                    "cpus must be at least 1. Is {}".format(cpus))
            config.numCPUs = cpus
        if memory is not None:
            try:
                memory = int(memory)
            except (ValueError, TypeError) as e:
                raise cfy_exc.NonRecoverableError(
                    "Invalid memory value: {}".format(e))
            if memory < 512:
                raise cfy_exc.NonRecoverableError(
                    "Memory must be at least 512MB. Is {}".format(memory))
            if memory % 128:
                raise cfy_exc.NonRecoverableError(
                    "Memory must be an integer multiple of 128. Is {}".format(
                        memory))
            config.memoryMB = memory

        task = server.obj.Reconfigure(spec=config)

        try:
            self._wait_for_task(task)
        except cfy_exc.NonRecoverableError as e:
            if 'configSpec.memoryMB' in e.args[0]:
                raise cfy_exc.NonRecoverableError(
                    "Memory error resizing Server. May be caused by "
                    "https://kb.vmware.com/kb/2008405 . If so the Server may "
                    "be resized while it is switched off.",
                    e,
                )
            raise

        ctx.logger.debug("Server '%s' resized with new number of "
                         "CPUs: %s and RAM: %s." % (server.name, cpus, memory))

    def get_server_ip(self, vm, network_name):
        ctx.logger.debug(
            'Getting server IP from {network}.'.format(
                network=network_name,
            )
        )

        for network in vm.guest.net:
            if not network.network:
                ctx.logger.warn(
                    'Ignoring device with MAC {mac} as it is not on a '
                    'vSphere network.'.format(
                        mac=network.macAddress,
                    )
                )
                continue
            if (
                network.network and
                network_name.lower() == network.network.lower() and
                len(network.ipAddress) > 0
            ):
                ip_address = get_ip_from_vsphere_nic_ips(network)
                # This should be debug, but left as info until CFY-4867 makes
                # logs more visible
                ctx.logger.info(
                    'Found {ip} from device with MAC {mac}'.format(
                        ip=ip_address,
                        mac=network.macAddress,
                    )
                )
                return ip_address

    def _task_guest_state_is_running(self, task):
        try:
            return task.info.result.guest.guestState == "running"
        except vmodl.fault.ManagedObjectNotFound:
            raise cfy_exc.NonRecoverableError(
                'Server failed to enter running state, task has been deleted '
                'by vCenter after failing.'
            )

    def _task_guest_has_networks(self, task, adaptermaps):
        # We should possibly be checking that it has the number of networks
        # expected here, but investigation will be required to confirm this
        # behaves as expected (and the VM state check later handles it anyway)
        if len(adaptermaps) == 0:
            return True
        else:
            if len(task.info.result.guest.net) > 0:
                return True
            else:
                return False

    def _wait_vm_running(self, task, adaptermaps):
        self._wait_for_task(task)

        while not self._task_guest_state_is_running(task) \
                or not self._task_guest_has_networks(task, adaptermaps):
            time.sleep(TASK_CHECK_SLEEP)


class NetworkClient(VsphereClient):

    def get_host_list(self, force_refresh=False):
        # Each invocation of this takes up to a few seconds, so try to avoid
        # calling it too frequently by caching
        if hasattr(self, 'host_list') and not force_refresh:
            return self.host_list
        self.host_list = self._get_hosts()
        return self.host_list

    def delete_port_group(self, name):
        ctx.logger.debug("Deleting port group {name}.".format(
                         name=name))
        for host in self.get_host_list():
            host.configManager.networkSystem.RemovePortGroup(name)
        ctx.logger.debug("Port group {name} was deleted.".format(
                         name=name))

    def get_vswitches(self):
        ctx.logger.debug('Getting list of vswitches')

        # We only want to list vswitches that are on all hosts, as we will try
        # to create port groups on the same vswitch on every host.
        vswitches = set()
        for host in self._get_hosts():
            conf = host.config
            current_host_vswitches = set()
            for vswitch in conf.network.vswitch:
                current_host_vswitches.add(vswitch.name)
            if len(vswitches) == 0:
                vswitches = current_host_vswitches
            else:
                vswitches = vswitches.union(current_host_vswitches)

        ctx.logger.debug('Found vswitches'.format(vswitches=vswitches))
        return vswitches

    def get_dvswitches(self):
        ctx.logger.debug('Getting list of dvswitches')

        # This does not currently address multiple datacenters (indeed,
        # much of this code will probably have issues in such an environment).
        dvswitches = self._get_dvswitches()
        dvswitches = [dvswitch.name for dvswitch in dvswitches]

        ctx.logger.debug('Found dvswitches'.format(dvswitches=dvswitches))
        return dvswitches

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Entering create port procedure.")
        runtime_properties = ctx.instance.runtime_properties
        if 'status' not in runtime_properties.keys():
            runtime_properties['status'] = 'preparing'

        vswitches = self.get_vswitches()

        if runtime_properties['status'] == 'preparing':
            if vswitch_name not in vswitches:
                if len(vswitches) == 0:
                    raise cfy_exc.NonRecoverableError(
                        'No valid vswitches found. '
                        'Every physical host in the datacenter must have the '
                        'same named vswitches available when not using '
                        'distributed vswitches.'
                    )
                else:
                    raise cfy_exc.NonRecoverableError(
                        '{vswitch} was not a valid vswitch name. The valid '
                        'vswitches are: {vswitches}'.format(
                            vswitch=vswitch_name,
                            vswitches=', '.join(vswitches),
                        )
                    )

        if runtime_properties['status'] in ('preparing', 'creating'):
            runtime_properties['status'] = 'creating'
            if 'created_on' not in runtime_properties.keys():
                runtime_properties['created_on'] = []

            hosts = [
                host for host in self.get_host_list()
                if host.name not in runtime_properties['created_on']
            ]

            for host in hosts:
                network_system = host.configManager.networkSystem
                specification = vim.host.PortGroup.Specification()
                specification.name = port_group_name
                specification.vlanId = vlan_id
                specification.vswitchName = vswitch_name
                vswitch = network_system.networkConfig.vswitch[0]
                specification.policy = vswitch.spec.policy
                ctx.logger.debug(
                    'Adding port group {group_name} to vSwitch '
                    '{vswitch_name} on host {host_name}'.format(
                        group_name=port_group_name,
                        vswitch_name=vswitch_name,
                        host_name=host.name,
                    )
                )
                try:
                    network_system.AddPortGroup(specification)
                except vim.fault.AlreadyExists:
                    # We tried to create it on a previous pass, but didn't see
                    # any confirmation (e.g. due to a problem communicating
                    # with the vCenter)
                    # However, we shouldn't have reached this point if it
                    # existed before we tried to create it anywhere, so it
                    # should be safe to proceed.
                    pass
                runtime_properties['created_on'].append(host.name)

            if self.port_group_is_on_all_hosts(port_group_name):
                runtime_properties['status'] = 'created'
            else:
                return ctx.operation.retry(
                    'Waiting for port group {name} to be created on all '
                    'hosts.'.format(
                        name=port_group_name,
                    )
                )

    def port_group_is_on_all_hosts(self, port_group_name, distributed=False):
        port_groups, hosts = self._get_port_group_host_count(
            port_group_name,
            distributed,
        )
        return hosts == port_groups

    def _get_port_group_host_count(self, port_group_name, distributed=False):
        hosts = self.get_host_list()
        host_count = len(hosts)

        port_groups = self._get_networks()

        if distributed:
            port_groups = [
                pg
                for pg in port_groups
                if self._port_group_is_distributed(pg)
            ]
        else:
            port_groups = [
                pg
                for pg in port_groups
                if not self._port_group_is_distributed(pg)
            ]

        # Observed to create multiple port groups in some circumstances,
        # but with different amounts of attached hosts
        port_groups = [pg for pg in port_groups if pg.name == port_group_name]

        port_group_counts = [len(pg.host) for pg in port_groups]

        port_group_count = sum(port_group_counts)

        ctx.logger.debug(
            '{type} group {name} found on {port_group_count} out of '
            '{host_count} hosts.'.format(
                type='Distributed port' if distributed else 'Port',
                name=port_group_name,
                port_group_count=port_group_count,
                host_count=host_count,
            )
        )

        return port_group_count, host_count

    def get_port_group_by_name(self, name):
        ctx.logger.debug("Getting port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    ctx.logger.debug("Port group(s) info: \n%s." %
                                     "".join("%s: %s" % item
                                             for item in
                                             vars(port_group).items()))
                    result.append(port_group)
        return result

    def create_dv_port_group(self, port_group_name, vlan_id, vswitch_name):
        ctx.logger.debug("Creating dv port group.")

        dvswitches = self.get_dvswitches()

        if vswitch_name not in dvswitches:
            if len(dvswitches) == 0:
                raise cfy_exc.NonRecoverableError(
                    'No valid dvswitches found. '
                    'A distributed virtual switch must exist for distributed '
                    'port groups to be used.'
                )
            else:
                raise cfy_exc.NonRecoverableError(
                    '{dvswitch} was not a valid dvswitch name. The valid '
                    'dvswitches are: {dvswitches}'.format(
                        dvswitch=vswitch_name,
                        dvswitches=', '.join(dvswitches),
                    )
                )

        dv_port_group_type = 'earlyBinding'
        dvswitch = self._get_obj_by_name(
            vim.DistributedVirtualSwitch,
            vswitch_name,
        )
        ctx.logger.debug("Distributed vSwitch info: \n%s." %
                         "".join("%s: %s" % item
                                 for item in
                                 vars(dvswitch).items()))
        vlan_spec = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(
            vlanId=vlan_id)
        port_settings = \
            vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
                vlan=vlan_spec)
        specification = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(
            name=port_group_name,
            defaultPortConfig=port_settings,
            type=dv_port_group_type)
        ctx.logger.debug(
            'Adding distributed port group {group_name} to dvSwitch '
            '{dvswitch_name}'.format(
                group_name=port_group_name,
                dvswitch_name=vswitch_name,
            )
        )
        task = dvswitch.obj.AddPortgroup(specification)
        self._wait_for_task(task)
        ctx.logger.debug("Port created.")

    def delete_dv_port_group(self, name):
        ctx.logger.debug("Deleting dv port group {name}.".format(
                         name=name))
        dv_port_group = self._get_obj_by_name(
            vim.dvs.DistributedVirtualPortgroup,
            name,
        )
        task = dv_port_group.obj.Destroy()
        self._wait_for_task(task)
        ctx.logger.debug("Port deleted.")


class StorageClient(VsphereClient):

    def create_storage(self, vm_id, storage_size):
        ctx.logger.debug("Entering create storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage:'
                ' invalid VM state - \'suspended\''
            )

        devices = []
        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.add
        virtual_device_spec.fileOperation =\
            vim.vm.device.VirtualDeviceSpec.FileOperation.create

        virtual_device_spec.device = vim.vm.device.VirtualDisk()
        virtual_device_spec.device.capacityInKB = storage_size * 1024 * 1024
        virtual_device_spec.device.capacityInBytes =\
            storage_size * 1024 * 1024 * 1024
        virtual_device_spec.device.backing =\
            vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        virtual_device_spec.device.backing.diskMode = 'Persistent'
        virtual_device_spec.device.backing.datastore = vm.datastore[0].obj

        vm_devices = vm.config.hardware.device
        vm_disk_filename = None
        vm_disk_filename_increment = 0
        vm_disk_filename_cur = None

        for vm_device in vm_devices:
            # Search all virtual disks
            if isinstance(vm_device, vim.vm.device.VirtualDisk):
                # Generate filename (add increment to VMDK base name)
                vm_disk_filename_cur = vm_device.backing.fileName
                p = re.compile('^(\[.*\]\s+.*\/.*)\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if vm_disk_filename is None:
                    vm_disk_filename = m.group(1)
                p = re.compile('^(.*)_([0-9]+)\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if m:
                    if m.group(2) is not None:
                        increment = int(m.group(2))
                        vm_disk_filename = m.group(1)
                        if increment > vm_disk_filename_increment:
                            vm_disk_filename_increment = increment

        # Exit error if VMDK filename undefined
        if vm_disk_filename is None:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage:'
                ' Invalid VMDK name - \'{0}\''.format(vm_disk_filename_cur)
            )

        # Set target VMDK filename
        vm_disk_filename =\
            vm_disk_filename +\
            "_" + str(vm_disk_filename_increment + 1) +\
            ".vmdk"

        # Search virtual SCSI controller
        controller = None
        num_controller = 0
        controller_types = (
            vim.vm.device.VirtualBusLogicController,
            vim.vm.device.VirtualLsiLogicController,
            vim.vm.device.VirtualLsiLogicSASController,
            vim.vm.device.ParaVirtualSCSIController)
        for vm_device in vm_devices:
            if isinstance(vm_device, controller_types):
                num_controller += 1
                controller = vm_device
        if num_controller != 1:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage: '
                'SCSI controller cannot be found or is present more than '
                'once.'
            )

        controller_key = controller.key

        # Set new unit number (7 cannot be used, and limit is 15)
        unit_number = None
        vm_vdisk_number = len(controller.device)
        if vm_vdisk_number < 7:
            unit_number = vm_vdisk_number
        elif vm_vdisk_number == 15:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to create storage: one SCSI controller '
                'cannot have more than 15 virtual disks.'
            )
        else:
            unit_number = vm_vdisk_number + 1

        virtual_device_spec.device.backing.fileName = vm_disk_filename
        virtual_device_spec.device.controllerKey = controller_key
        virtual_device_spec.device.unitNumber = unit_number
        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.obj.Reconfigure(spec=config_spec)
        ctx.logger.debug("Task info: \n%s." % prepare_for_log(vars(task)))
        self._wait_for_task(task)

        # Get the SCSI bus and unit IDs
        scsi_controllers = []
        disks = []
        # Use the device list from the platform rather than the cache because
        # we just created a disk so it won't be in the cache
        for device in vm.obj.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualSCSIController):
                scsi_controllers.append(device)
            elif isinstance(device, vim.vm.device.VirtualDisk):
                disks.append(device)
        # Find the disk we just created
        for disk in disks:
            if disk.backing.fileName == vm_disk_filename:
                unit = disk.unitNumber
                bus_id = None
                for controller in scsi_controllers:
                    if controller.key == disk.controllerKey:
                        bus_id = controller.busNumber
                        break
                # We found the right disk, we can't do any better than this
                break
        if bus_id is None:
            raise cfy_exc.NonRecoverableError(
                'Could not find SCSI bus ID for disk with filename: '
                '{file}'.format(file=vm_disk_filename)
            )
        else:
            # Give the SCSI ID in the usual format, e.g. 0:1
            scsi_id = ':'.join((str(bus_id), str(unit)))

        return vm_disk_filename, scsi_id

    def delete_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                "Error during trying to delete storage: invalid VM state - "
                "'suspended'"
            )

        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.remove
        virtual_device_spec.fileOperation =\
            vim.vm.device.VirtualDeviceSpec.FileOperation.destroy

        devices = []

        device_to_delete = None

        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualDisk)\
                    and device.backing.fileName == storage_file_name:
                device_to_delete = device

        if device_to_delete is None:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to delete storage: storage not found')

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.obj.Reconfigure(spec=config_spec)
        ctx.logger.debug("Task info: \n%s." % prepare_for_log(vars(task)))
        self._wait_for_task(task)

    def get_storage(self, vm_id, storage_file_name):
        ctx.logger.debug("Entering get storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if vm:
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk)\
                        and device.backing.fileName == storage_file_name:
                    ctx.logger.debug(
                        "Device info: \n%s." % prepare_for_log(vars(device))
                    )
                    return device
        return None

    def resize_storage(self, vm_id, storage_filename, storage_size):
        ctx.logger.debug("Entering resize storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise cfy_exc.NonRecoverableError(
                'Error during trying to resize storage: invalid VM state'
                ' - \'suspended\'')

        disk_to_resize = None
        devices = vm.config.hardware.device
        for device in devices:
            if (isinstance(device, vim.vm.device.VirtualDisk) and
                    device.backing.fileName == storage_filename):
                disk_to_resize = device

        if disk_to_resize is None:
            raise cfy_exc.NonRecoverableError(
                'Error during trying to resize storage: storage not found')

        updated_devices = []
        virtual_device_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_device_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.edit

        virtual_device_spec.device = disk_to_resize
        virtual_device_spec.device.capacityInKB = storage_size * 1024 * 1024
        virtual_device_spec.device.capacityInBytes =\
            storage_size * 1024 * 1024 * 1024

        updated_devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = updated_devices

        task = vm.obj.Reconfigure(spec=config_spec)
        ctx.logger.debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        self._wait_for_task(task)
        ctx.logger.debug("Storage resized to a new size %s." % storage_size)


def with_server_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        server_client = ServerClient().get(config=config)
        kw['server_client'] = server_client
        return f(*args, **kw)
    return wrapper


def with_network_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        network_client = NetworkClient().get(config=config)
        kw['network_client'] = network_client
        return f(*args, **kw)
    return wrapper


def with_storage_client(f):
    @wraps(f)
    def wrapper(*args, **kw):
        config = ctx.node.properties.get('connection_config')
        storage_client = StorageClient().get(config=config)
        kw['storage_client'] = storage_client
        return f(*args, **kw)
    return wrapper
