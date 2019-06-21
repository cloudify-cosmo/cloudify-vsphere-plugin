# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
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

from __future__ import division

# Stdlib imports
import atexit
import os
import re
import ssl
import time
import urllib
import netaddr
from collections import MutableMapping
from copy import copy
from functools import wraps

# Third party imports
import yaml
from netaddr import IPNetwork
from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect
from pyVmomi import vim, vmodl
import requests

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common.constants import (
    DEFAULT_CONFIG_PATH,
    IP,
    NETWORKS,
    NETWORK_ID,
    NETWORK_MTU,
    TASK_CHECK_SLEEP,
    VSPHERE_SERVER_CLUSTER_NAME,
    VSPHERE_SERVER_HYPERVISOR_HOSTNAME,
    VSPHERE_RESOURCE_NAME,
    NETWORK_CREATE_ON,
    NETWORK_STATUS,
)
from collections import namedtuple
from cloudify_vsphere.utils.feedback import logger, prepare_for_log


def get_ip_from_vsphere_nic_ips(nic, ignore_local=True):
    for ip in nic.ipAddress:
        if (ip.startswith('169.254.') or ip.lower().startswith('fe80::')) \
                and ignore_local:
            # This is a locally assigned IPv4 or IPv6 address and thus we
            # will assume it is not routable
            logger().debug(
                'Found locally assigned IP {ip}. Skipping.'.format(ip=ip))
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
    # Hard-coded to old path so old manager blueprints aren't broken
    CONNECTION_CONFIG_PATH_DEFAULT = '/root/connection_config.yaml'

    _path_options = [
        {'source': '/root/connection_config.yaml', 'warn': True},
        {'source': '~/connection_config.yaml', 'warn': True},
        {'source': DEFAULT_CONFIG_PATH, 'warn': False},
        {'env': True, 'source': 'CONNECTION_CONFIG_PATH', 'warn': True},
        {'env': True, 'source': 'CFY_VSPHERE_CONFIG_PATH', 'warn': False},
    ]

    def _find_config_file(self):
        selected = DEFAULT_CONFIG_PATH
        warnings = []

        for path in self._path_options:
            source = path['source']
            if path.get('env'):
                source = os.getenv(source)
            if source:
                source = os.path.expanduser(source)
                if os.path.isfile(source):
                    selected = source
                    if path['warn']:
                        warnings.append(path['source'])

        if warnings:
            logger().warn(
                "Deprecated configuration options were found: {}".format(
                    "; ".join(warnings)),
            )

        return selected

    def get(self):
        cfg = {}
        config_path = self._find_config_file()
        try:
            with open(config_path) as f:
                cfg = yaml.load(f.read())
        except IOError:
            logger().warn(
                "Unable to read configuration file %s." % (config_path))

        return cfg


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


class CustomValues(MutableMapping):
    """dict interface to ManagedObject customValue"""

    def __init__(self, client, thing):
        """
        client: a VsphereClient instance
        thing: a NamedTuple containing a ManagedObject-derived class as its
        `obj` attribute: as supplied by `client._get_obj_by_name`
        """
        self.client = client
        self.thing = thing

    def __getitem__(self, key):
        key_id = self._get_key_id(key)
        for value in self.thing.obj.customValue:
            if value.key == key_id:
                return value.value
        raise KeyError(key)

    def __setitem__(self, key, value):
        self._get_key_id(key, create=True)
        return self.thing.obj.setCustomValue(key, value)

    def __delitem__(self, key):
        raise NonRecoverableError("Unable to unset custom values")

    def __iter__(self):
        for value in self.thing.obj.customValue:
            yield self._get_key_name(value.key)

    def __len__(self):
        return len(self.thing.obj.customValue)

    def _get_key_id(self, k, create=False):
        for key in self.client._get_custom_keys():
            if key.name == k:
                return key.key
        if create:
            try:
                key = (
                    self.client.si.content.customFieldsManager.
                    AddCustomFieldDef)(name=k)
            except vim.fault.DuplicateName:
                self.client._get_custom_keys(use_cache=False)
                return self._get_key_id(k, create=create)
            return key.key
        raise KeyError(k)

    def _get_key_name(self, k):
        for key in self.client._get_custom_keys():
            if key.key == k:
                return key.name
        raise ValueError(k)


class VsphereClient(object):

    def __init__(self):
        self._cache = {}

    def get(self, config=None, *args, **kw):
        static_config = Config().get()
        self.cfg = {}
        self.cfg.update(static_config)
        if config:
            self.cfg.update(config)
        ret = self.connect(self.cfg)
        ret.format = 'yaml'
        return ret

    def connect(self, cfg):
        host = cfg['host']
        username = cfg['username']
        password = cfg['password']
        port = cfg['port']
        certificate_path = cfg.get('certificate_path')
        # Until the next major release this will have limited effect, but is
        # in place to allow a clear path to the next release for users
        allow_insecure = cfg.get('allow_insecure', False)
        ssl_context = None

        if certificate_path and allow_insecure:
            raise NonRecoverableError(
                'Cannot connect when certificate_path and allow_insecure '
                'are both set. Unable to determine whether connection should '
                'be secure or insecure.'
            )
        elif certificate_path:
            if not hasattr(ssl, '_create_default_https_context'):
                raise NonRecoverableError(
                    'Cannot create secure connection with this version of '
                    'python. This functionality requires at least python '
                    '2.7.9 and has been confirmed to work on at least 2.7.12.'
                )

            if not os.path.exists(certificate_path):
                raise NonRecoverableError(
                    'Certificate was not found in {path}'.format(
                        path=certificate_path,
                    )
                )
            elif not os.path.isfile(certificate_path):
                raise NonRecoverableError(
                    'Found directory at {path}, but the certificate_path '
                    'must be a file.'.format(
                        path=certificate_path,
                    )
                )
            try:
                # We want to load the cert into the existing default context
                # in case any other python modules have already defined their
                # default https context.
                ssl_context = ssl._create_default_https_context()
                if ssl_context.verify_mode == 0:
                    raise NonRecoverableError(
                        'Default SSL context is not set to verify. '
                        'Cannot use a certificate while other imported '
                        'modules are disabling verification on the default '
                        'SSL context.'
                    )
                ssl_context.load_verify_locations(certificate_path)
            except ssl.SSLError as err:
                if 'unknown error' in str(err).lower():
                    raise NonRecoverableError(
                        'Could not create SSL context with provided '
                        'certificate {path}. This problem may be caused by '
                        'the certificate not being in the correct format '
                        '(PEM).'.format(
                            host=host,
                            path=certificate_path,
                        )
                    )
                else:
                    raise
        elif not allow_insecure:
            logger().warn(
                'DEPRECATED: certificate_path was not supplied. '
                'A certificate will be required in the next major '
                'release of the plugin if allow_insecure is not set '
                'to true.'
            )

        try:
            if allow_insecure:
                logger().warn(
                    'SSL verification disabled for all legacy code. '
                    'Please note that this may result in other code '
                    'from the same blueprint running with reduced '
                    'security.'
                )
                self.si = SmartConnectNoSSL(host=host,
                                            user=username,
                                            pwd=password,
                                            port=int(port))
            else:
                self.si = SmartConnect(host=host,
                                       user=username,
                                       pwd=password,
                                       port=int(port),
                                       sslContext=ssl_context)
            atexit.register(Disconnect, self.si)
            return self
        except vim.fault.InvalidLogin:
            raise NonRecoverableError(
                "Could not login to vSphere on {host} with provided "
                "credentials".format(host=host)
            )
        except vim.fault.HostConnectFault as err:
            if 'certificate verify failed' in err.msg:
                raise NonRecoverableError(
                    'Could not connect to vSphere on {host} with provided '
                    'certificate {path}. Certificate was not valid.'.format(
                        host=host,
                        path=certificate_path,
                    )
                )
            else:
                raise

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
        the_dict['_values'] = set(vals)
        for item in keys:
            key_name = item[0]
            sub_keys = item[1:]
            dict_entry = the_dict.get(key_name, {'_values': set()})
            update_dict = self._convert_props_list_to_dict(
                sub_keys
            )
            the_dict[key_name] = self._merge_props_dicts(
                dict_entry,
                update_dict,
            )
        return the_dict

    def _merge_props_dicts(self, dict1, dict2):
        new_dict = {}
        keys = set(dict1.keys() + dict2.keys())
        keys.remove('_values')

        new_dict['_values'] = dict1['_values'] | dict2['_values']

        for key in keys:
            new_dict[key] = self._merge_props_dicts(
                dict1.get(key, {'_values': set()}),
                dict2.get(key, {'_values': set()})
            )

        return new_dict

    def _get_platform_sub_results(self, platform_results, target_key):
        sub_results = {}
        for key, value in platform_results.items():
            key_components = key.split('.', 1)
            if key_components[0] == target_key:
                sub_results[key_components[1]] = value
        return sub_results

    def _get_normalised_name(self, name, tolower=True):
        """
            Get the normalised form of a platform entity's name.
        """
        name = urllib.unquote(name)
        return name.lower() if tolower else name

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

        if 'name' in args.keys():
            args['name'] = self._get_normalised_name(args['name'], False)

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
                message = (
                    'Could not retrieve all details for {type} object. '
                    '{err} was missing.'.format(
                        type=entity_name,
                        err=str(err)
                    )
                )
                if hasattr(result, 'name'):
                    message += (
                        ' Object name was {name}.'.format(name=result.name)
                    )
                if hasattr(result, '_moId'):
                    message += (
                        ' Object ID was {id}.'.format(id=result._moId)
                    )
                if skip_broken_objects:
                    ctx.logger.warn(message)
                else:
                    raise NonRecoverableError(message)

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

        if 'name' in this_pool.keys():
            this_pool['name'] = self._get_normalised_name(this_pool['name'],
                                                          False)

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

    def _get_vm_folders(self, use_cache=True):
        properties = [
            'name'
        ]

        return self._get_entity(
            entity_name='vm_folder',
            props=properties,
            vimtype=vim.Folder,
            use_cache=use_cache,
        )

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
                raise NonRecoverableError(
                    'Could not find any relationships to a node called '
                    '"{name}", so {prop} could not be retrieved.'.format(
                        name=network['name'],
                        prop=NETWORK_ID,
                    )
                )
            elif net_id is None:
                raise NonRecoverableError(
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
                raise NonRecoverableError(
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
            if 'name' in item.keys():
                item['name'] = self._get_normalised_name(item['name'], False)

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
            'config.hardware.memoryMB',
            'config.hardware.numCPU',
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
            'summary.runtime.inMaintenanceMode',
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
            skip_broken_objects=True,
        )

    def _get_hosts_in_tree(self, host_folder):
        def get_vmware_hosts(tree_node):
            # Traverse the tree to find any hosts.
            hosts = []

            if hasattr(tree_node, "host"):
                # If we find hosts under this node we are done.
                hosts.extend(list(tree_node.host))

            elif hasattr(tree_node, "childEntity"):
                # If there are no hosts look under its children
                for entity in tree_node.childEntity:
                    hosts.extend(get_vmware_hosts(entity))

            return hosts

        # Get all of the hosts in this hosts folder, that includes looking
        # in subfolders and clusters.
        vmware_hosts = get_vmware_hosts(host_folder)

        # Cloudify uses a slightly different style of object to the raw VMWare
        # API. To convert one to the other look up object IDs and compare.
        vmware_host_ids = [host._GetMoId() for host in vmware_hosts]

        cloudify_host_dict = {cloudify_host.obj._GetMoId(): cloudify_host
                              for cloudify_host in self._get_hosts()}

        cloudify_hosts = [cloudify_host_dict[id] for id in vmware_host_ids]

        return cloudify_hosts

    def _convert_vmware_port_group_to_cloudify(self, port_group):
        port_group_id = port_group._moId

        for cloudify_port_group in self._get_networks():
            if cloudify_port_group.obj._moId == port_group_id:
                break
        else:
            raise RuntimeError(
                "Couldn't find cloudify representation of port group {name}"
                .format(name=port_group.name))

        return cloudify_port_group

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
            vim.Folder: self._get_vm_folders,
        }.get(vimtype)
        if getter_method is None:
            raise NonRecoverableError(
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

        name = self._get_normalised_name(name)

        for entity in entities:
            if name == entity.name.lower():
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
            logger().debug('Task state {state}'
                           .format(state=task.info.state))
        if task.info.state != vim.TaskInfo.State.success:
            raise NonRecoverableError(
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
        logger().debug('Getting NIC list')
        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                nics.append(dev)

        logger().debug('Got NICs: {nics}'.format(nics=nics))
        networks = []
        for nic in nics:
            logger().debug('Checking details for NIC {nic}'.format(nic=nic))
            distributed = hasattr(nic.backing, 'port') and isinstance(
                nic.backing.port,
                vim.dvs.PortConnection,
            )

            network_name = None
            if distributed:
                mapping_id = nic.backing.port.portgroupKey
                logger().debug(
                    'Found NIC was on distributed port group with port group '
                    'key {key}'.format(key=mapping_id)
                )
                for network in vm.network:
                    if hasattr(network, 'key'):
                        logger().debug(
                            'Checking for match on network with key: '
                            '{key}'.format(key=network.key)
                        )
                        if mapping_id == network.key:
                            network_name = network.name
                            logger().debug(
                                'Found NIC was distributed and was on '
                                'network {network}'.format(
                                    network=network_name,
                                )
                            )
            else:
                # If not distributed, the port group name can be retrieved
                # directly
                network_name = nic.backing.deviceName
                logger().debug(
                    'Found NIC was on port group {network}'.format(
                        network=network_name,
                    )
                )

            if network_name is None:
                raise NonRecoverableError(
                    'Could not get network name for device with MAC address '
                    '{mac} on VM {vm}'.format(mac=nic.macAddress, vm=vm.name)
                )

            networks.append({
                'name': network_name,
                'distributed': distributed,
                'mac': nic.macAddress,
            })

        return networks

    def _get_custom_keys(self, use_cache=True):
        if not use_cache or 'custom_keys' not in self._cache:
            self._cache['custom_keys'] = (
                self.si.content.customFieldsManager.field
            )

        return self._cache['custom_keys']

    def custom_values(self, thing):
        return CustomValues(self, thing)

    def add_custom_values(self, thing, attributes):
        if attributes:
            values = self.custom_values(thing)
            values.update(attributes)
            logger().debug('Added custom attributes')


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
        logger().debug(
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
            logger().warn(
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
                         networks):
        """
            Make sure we can actually continue with the inputs given.
            If we can't, we want to report all of the issues at once.
        """
        logger().debug('Validating inputs for this platform.')
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

        logger().debug('Checking template exists.')
        template_vm = self._get_obj_by_name(vim.VirtualMachine,
                                            template_name)
        if template_vm is None:
            issues.append("VM template {0} could not be found.".format(
                template_name
            ))

        logger().debug('Checking resource pool exists.')
        resource_pool = self._get_obj_by_name(
            vim.ResourcePool,
            resource_pool_name,
        )
        if resource_pool is None:
            issues.append("Resource pool {0} could not be found.".format(
                resource_pool_name,
            ))

        logger().debug('Checking datacenter exists.')
        datacenter = self._get_obj_by_name(vim.Datacenter,
                                           datacenter_name)
        if datacenter is None:
            issues.append("Datacenter {0} could not be found.".format(
                datacenter_name
            ))

        logger().debug(
            'Checking networks exist.'
        )
        port_groups, distributed_port_groups = self._get_port_group_names()
        for network in networks:
            try:
                network_name = self._get_connected_network_name(network)
            except NonRecoverableError as err:
                issues.append(str(err))
                continue
            network_name = self._get_normalised_name(network_name)
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
                if network_name not in distributed_port_groups:
                    if network_name in port_groups:
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
                if network_name not in port_groups:
                    if network_name in distributed_port_groups:
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

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise NonRecoverableError(message)

    def _validate_windows_properties(
            self,
            custom_sysprep,
            windows_organization,
            windows_password,
            ):
        issues = []

        if windows_password == '':
            # Avoid falsey comparison on blank password
            windows_password = True
        if windows_password == '':
            # Avoid falsey comparison on blank password
            windows_password = True
        if custom_sysprep is not None:
            if windows_password:
                issues.append(
                    'custom_sysprep answers data has been provided, but a '
                    'windows_password was supplied. If using custom sysprep, '
                    'no other windows settings are usable.'
                )
        elif not windows_password and custom_sysprep is None:
            if not windows_password:
                issues.append(
                    'Windows password must be set when a custom sysprep is '
                    'not being performed. Please supply a windows_password '
                    'using either properties.windows_password or '
                    'properties.agent_config.password'
                )

        if len(windows_organization) == 0:
            issues.append('windows_organization property must not be blank')
        if len(windows_organization) > 64:
            issues.append(
                'windows_organization property must be 64 characters or less')

        if issues:
            issues.insert(0, 'Issues found while validating inputs:')
            message = ' '.join(issues)
            raise NonRecoverableError(message)

    def _add_network(self, network, datacenter):
        network_name = network['name']
        normalised_network_name = self._get_normalised_name(network_name)
        switch_distributed = network['switch_distributed']
        mac_address = network.get('mac_address')

        use_dhcp = network['use_dhcp']
        if switch_distributed:
            for port_group in datacenter.obj.network:
                # Make sure that we are comparing normalised network names.
                normalised_port_group_name = self._get_normalised_name(
                    port_group.name
                )
                if normalised_port_group_name == normalised_network_name:
                    network_obj = \
                        self._convert_vmware_port_group_to_cloudify(port_group)
                    break
            else:
                logger().warning(
                    "Network {name} couldn't be found.  Only found {networks}."
                    .format(name=network_name, networks=repr([
                        net.name for net in datacenter.obj.network])))
                network_obj = None
        else:
            network_obj = self._get_obj_by_name(
                vim.Network,
                network_name,
            )
        if network_obj is None:
            raise NonRecoverableError(
                'Network {0} could not be found'.format(network_name))
        nicspec = vim.vm.device.VirtualDeviceSpec()
        # Info level as this is something that was requested in the
        # blueprint
        logger().info(
            'Adding network interface on {name}'.format(
                name=network_name))
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
        if mac_address:
            nicspec.device.macAddress = mac_address

        if use_dhcp:
            guest_map = vim.vm.customization.AdapterMapping()
            guest_map.adapter = vim.vm.customization.IPSettings()
            guest_map.adapter.ip = vim.vm.customization.DhcpIpGenerator()
        else:
            nw = IPNetwork(network["network"])
            guest_map = vim.vm.customization.AdapterMapping()
            guest_map.adapter = vim.vm.customization.IPSettings()
            guest_map.adapter.ip = vim.vm.customization.FixedIp()
            guest_map.adapter.ip.ipAddress = network[IP]
            guest_map.adapter.gateway = network["gateway"]
            guest_map.adapter.subnetMask = str(nw.netmask)
        return nicspec, guest_map

    def _update_vm(self, server, cdrom_image=None, remove_networks=False):
        # update vm with attach cdrom image and remove network adapters
        devices = []
        ide_controller = None
        cdrom_attached = False
        for device in server.config.hardware.device:
            # delete network interface
            if remove_networks and hasattr(device, 'macAddress'):
                nicspec = vim.vm.device.VirtualDeviceSpec()
                nicspec.device = device
                logger().warn(
                    'Removing network adapter from template. '
                    'Template should have no attached adapters.')
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.remove
                devices.append(nicspec)
            # remove cdrom when we have cloudinit
            elif (
                isinstance(device, vim.vm.device.VirtualCdrom) and
                cdrom_image
            ):
                logger().warn(
                    'Edit cdrom from template. '
                    'Template should have no inserted cdroms.')
                cdrom_attached = True
                # skip if cdrom is already attached
                if isinstance(
                    device.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo
                ):
                    if str(device.backing.fileName) == str(cdrom_image):
                        logger().info("Same cdrom is already attached.")
                        continue
                cdrom = vim.vm.device.VirtualDeviceSpec()
                cdrom.device = device
                device.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(
                    fileName=cdrom_image)
                cdrom.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.edit
                connectable = vim.vm.device.VirtualDevice.ConnectInfo()
                connectable.allowGuestControl = True
                connectable.startConnected = True
                device.connectable = connectable
                devices.append(cdrom)
                ide_controller = device.controllerKey
            # ide controller
            elif isinstance(device, vim.vm.device.VirtualIDEController):
                # skip fully attached controllers
                if len(device.device) < 2:
                    ide_controller = device.key

        # attach cdrom
        if cdrom_image and not cdrom_attached:
            if not ide_controller:
                raise NonRecoverableError(
                    'IDE controller is required for attach cloudinit cdrom.')

            cdrom_device = vim.vm.device.VirtualDeviceSpec()
            cdrom_device.operation = \
                vim.vm.device.VirtualDeviceSpec.Operation.add
            connectable = vim.vm.device.VirtualDevice.ConnectInfo()
            connectable.allowGuestControl = True
            connectable.startConnected = True

            cdrom = vim.vm.device.VirtualCdrom()
            cdrom.controllerKey = ide_controller
            cdrom.key = -1
            cdrom.connectable = connectable
            cdrom.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(
                fileName=cdrom_image)
            cdrom_device.device = cdrom
            devices.append(cdrom_device)
        return devices

    def update_server(self, server, cdrom_image=None, extra_config=None):
        # Attrach cdrom image to vm without change networks list
        devices_changes = self._update_vm(server, cdrom_image=cdrom_image,
                                          remove_networks=False)
        if devices_changes or extra_config:
            spec = vim.vm.ConfigSpec()
            # changed devices
            if devices_changes:
                spec.deviceChange = devices_changes
            # add extra config
            if extra_config and isinstance(extra_config, dict):
                logger().debug('Extra config: {config}'
                               .format(config=repr(extra_config)))
                for k in extra_config:
                    spec.extraConfig.append(
                        vim.option.OptionValue(key=k, value=extra_config[k]))
            task = server.obj.ReconfigVM_Task(spec=spec)
            self._wait_for_task(task)

    def create_server(
            self,
            auto_placement,
            cpus,
            datacenter_name,
            memory,
            networks,
            resource_pool_name,
            template_name,
            vm_name,
            windows_password,
            windows_organization,
            windows_timezone,
            agent_config,
            custom_sysprep,
            custom_attributes,
            os_type='linux',
            domain=None,
            dns_servers=None,
            allowed_hosts=None,
            allowed_clusters=None,
            allowed_datastores=None,
            cdrom_image=None,
            vm_folder=None,
            extra_config=None,
            enable_start_vm=True,
            ):
        logger().debug(
            "Entering create_server with parameters %s"
            % prepare_for_log(locals()))

        self._validate_inputs(
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
            allowed_datastores=allowed_datastores,
            template_name=template_name,
            networks=networks,
            resource_pool_name=resource_pool_name,
            datacenter_name=datacenter_name,
        )

        # If cpus and memory are not specified, take values from the template.
        template_vm = self._get_obj_by_name(vim.VirtualMachine, template_name)
        if not cpus:
            cpus = template_vm.config.hardware.numCPU

        if not memory:
            memory = template_vm.config.hardware.memoryMB

        # Correct the network name for all networks from relationships
        for network in networks:
            network['name'] = self._get_connected_network_name(network)

        datacenter = self._get_obj_by_name(vim.Datacenter,
                                           datacenter_name)

        candidate_hosts = self.find_candidate_hosts(
            datacenter=datacenter,
            resource_pool=resource_pool_name,
            vm_cpus=cpus,
            vm_memory=memory,
            vm_networks=networks,
            allowed_hosts=allowed_hosts,
            allowed_clusters=allowed_clusters,
        )

        host, datastore = self.select_host_and_datastore(
            candidate_hosts=candidate_hosts,
            vm_memory=memory,
            template=template_vm,
            allowed_datastores=allowed_datastores,
        )
        ctx.instance.runtime_properties[
            VSPHERE_SERVER_HYPERVISOR_HOSTNAME] = host.name
        ctx.instance.runtime_properties[
            VSPHERE_SERVER_CLUSTER_NAME] = host.parent.name
        logger().debug(
            'Using host {host} and datastore {ds} for deployment.'.format(
                host=host.name,
                ds=datastore.name,
            )
        )

        adaptermaps = []

        resource_pool = self.get_resource_pool(
            host=host,
            resource_pool_name=resource_pool_name,
        )

        if not vm_folder:
            destfolder = datacenter.vmFolder
        else:
            folder = self._get_obj_by_name(vim.Folder, vm_folder)
            if not folder:
                raise NonRecoverableError(
                    'Could not use vm_folder "{name}" as no '
                    'vm folder by that name exists!'.format(
                        name=vm_folder,
                    )
                )
            destfolder = folder.obj

        relospec = vim.vm.RelocateSpec()
        relospec.datastore = datastore.obj
        relospec.pool = resource_pool.obj
        if not auto_placement:
            logger().warn(
                'Disabled autoplacement is not recomended for a cluster.'
            )
            relospec.host = host.obj

        # attach cdrom image and remove all networks
        devices = self._update_vm(template_vm, cdrom_image=cdrom_image,
                                  remove_networks=True)

        port_groups, distributed_port_groups = self._get_port_group_names()

        for network in networks:
            nicspec, guest_map = self._add_network(network, datacenter)
            devices.append(nicspec)
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
        clonespec.powerOn = enable_start_vm
        clonespec.template = False

        # add extra config
        if extra_config and isinstance(extra_config, dict):
            logger().debug('Extra config: {config}'
                           .format(config=repr(extra_config)))
            for k in extra_config:
                clonespec.extraConfig.append(
                    vim.option.OptionValue(key=k, value=extra_config[k]))

        if adaptermaps:
            logger().debug(
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
                if not windows_password:
                    if not agent_config:
                        agent_config = {}
                    windows_password = agent_config.get('password')

                self._validate_windows_properties(
                        custom_sysprep,
                        windows_organization,
                        windows_password,
                        )

                if custom_sysprep is not None:
                    ident = vim.vm.customization.SysprepText()
                    ident.value = custom_sysprep
                else:
                    # We use GMT without daylight savings if no timezone is
                    # supplied, as this is as close to UTC as we can do
                    if not windows_timezone:
                        windows_timezone = 90

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
                    ident.userData.orgName = windows_organization
                    ident.userData.productId = ""

                    # Configure guiUnattended
                    ident.guiUnattended.autoLogon = False
                    ident.guiUnattended.password = (
                        vim.vm.customization.Password()
                    )
                    ident.guiUnattended.password.plainText = True
                    ident.guiUnattended.password.value = windows_password
                    ident.guiUnattended.timeZone = windows_timezone

                # Adding windows options
                options = vim.vm.customization.WinOptions()
                options.changeSID = True
                options.deleteAccounts = False
                customspec.options = options
            elif os_type == 'solaris':
                ident = None
                logger().info(
                    'Customization of the Solaris OS is unsupported by '
                    ' vSphere. Guest additions are required/supported.')
            else:
                ident = None
                logger().info(
                    'os_type {os_type} was specified, but only "windows", '
                    '"solaris" and "linux" are supported. Customization is '
                    'unsupported.'
                    .format(os_type=os_type)
                )

            if ident:
                customspec.identity = ident

                globalip = vim.vm.customization.GlobalIPSettings()
                if dns_servers:
                    globalip.dnsServerList = dns_servers
                customspec.globalIPSettings = globalip

                clonespec.customization = customspec
        logger().info(
            'Cloning {server} from {template}.'.format(
                server=vm_name, template=template_name))
        logger().debug('Cloning with clonespec: {spec}'
                       .format(spec=repr(clonespec)))
        task = template_vm.obj.Clone(folder=destfolder,
                                     name=vm_name,
                                     spec=clonespec)
        try:
            logger().debug(
                "Task info: {task}".format(task=repr(task)))
            if enable_start_vm:
                logger().info('VM created in running state')
                self._wait_vm_running(task, adaptermaps, os_type == "other")
            else:
                logger().info('VM created in stopped state')
                self._wait_for_task(task)
        except task.info.error:
            raise NonRecoverableError(
                "Error during executing VM creation task. VM name: \'{0}\'."
                .format(vm_name))

        vm = self._get_obj_by_name(
            vim.VirtualMachine,
            vm_name,
            use_cache=False,
        )
        ctx.instance.runtime_properties[NETWORKS] = \
            self.get_vm_networks(vm)
        logger().debug('Updated runtime properties with network information')

        self.add_custom_values(vm, custom_attributes or {})

        return task.info.result

    def suspend_server(self, server):
        if self.is_server_suspended(server.obj):
            logger().info("Server '{}' already suspended.".format(server.name))
            return
        if self.is_server_poweredoff(server):
            logger().info("Server '{}' is powered off so will not be "
                          "suspended.".format(server.name))
            return
        logger().debug("Entering server suspend procedure.")
        task = server.obj.Suspend()
        self._wait_for_task(task)
        logger().debug("Server is suspended.")

    def start_server(self, server):
        if self.is_server_poweredon(server):
            logger().info("Server '{}' already running".format(server.name))
            return
        logger().debug("Entering server start procedure.")
        task = server.obj.PowerOn()
        self._wait_for_task(task)
        logger().debug("Server is now running.")

    def shutdown_server_guest(
        self, server,
        timeout=TASK_CHECK_SLEEP,
        max_wait_time=300,
    ):
        if self.is_server_poweredoff(server):
            logger().info("Server '{}' already stopped".format(server.name))
            return
        logger().debug("Entering server shutdown procedure.")
        server.obj.ShutdownGuest()
        for _ in range(max_wait_time // timeout):
            time.sleep(timeout)
            if self.is_server_poweredoff(server):
                break
        else:
            raise NonRecoverableError(
                "Server still running after {time}s timeout.".format(
                    time=max_wait_time,
                ))
        logger().debug("Server is now shut down.")

    def stop_server(self, server):
        if self.is_server_poweredoff(server):
            logger().info("Server '{}' already stopped".format(server.name))
            return
        logger().debug("Entering stop server procedure.")
        task = server.obj.PowerOff()
        self._wait_for_task(task)
        logger().debug("Server is now stopped.")

    def backup_server(self, server, snapshot_name, description):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
            if snapshot:
                raise NonRecoverableError(
                    "Snapshot {snapshot_name} already exists."
                    .format(snapshot_name=snapshot_name,))

        task = server.obj.CreateSnapshot(
            snapshot_name, description=description,
            memory=False, quiesce=False)
        self._wait_for_task(task)

    def get_snapshot_by_name(self, snapshots, snapshot_name):
        for snapshot in snapshots:
            if snapshot.name == snapshot_name:
                return snapshot
            else:
                subsnapshot = self.get_snapshot_by_name(
                    snapshot.childSnapshotList, snapshot_name)
                if subsnapshot:
                    return subsnapshot
        return False

    def restore_server(self, server, snapshot_name):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
        else:
            snapshot = None
        if not snapshot:
            raise NonRecoverableError(
                "No snapshots found with name: {snapshot_name}."
                .format(snapshot_name=snapshot_name,))

        task = snapshot.snapshot.RevertToSnapshot_Task()
        self._wait_for_task(task)

    def remove_backup(self, server, snapshot_name):
        if server.obj.snapshot:
            snapshot = self.get_snapshot_by_name(
                server.obj.snapshot.rootSnapshotList, snapshot_name)
        else:
            snapshot = None
        if not snapshot:
            raise NonRecoverableError(
                "No snapshots found with name: {snapshot_name}."
                .format(snapshot_name=snapshot_name,))

        if snapshot.childSnapshotList:
            subsnapshots = [snap.name for snap in snapshot.childSnapshotList]
            raise NonRecoverableError(
                "Sub snapshots {subsnapshots} found for {snapshot_name}. "
                "You should remove subsnaphots before remove current."
                .format(snapshot_name=snapshot_name,
                        subsnapshots=repr(subsnapshots)))

        task = snapshot.snapshot.RemoveSnapshot_Task(True)
        self._wait_for_task(task)

    def reset_server(self, server):
        if self.is_server_poweredoff(server):
            logger().info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server)
        logger().debug("Entering stop server procedure.")
        task = server.obj.Reset()
        self._wait_for_task(task)
        logger().debug("Server has been reset")

    def reboot_server(
        self, server,
        timeout=TASK_CHECK_SLEEP,
        max_wait_time=300,
    ):
        if self.is_server_poweredoff(server):
            logger().info(
                "Server '{}' currently stopped, starting.".format(server.name))
            return self.start_server(server)
        logger().debug("Entering reboot server procedure.")
        start_bootTime = server.obj.runtime.bootTime
        server.obj.RebootGuest()
        for _ in range(max_wait_time // timeout):
            time.sleep(timeout)
            if server.obj.runtime.bootTime > start_bootTime:
                break
        else:
            raise NonRecoverableError(
                "Server still running after {time}s timeout.".format(
                    time=max_wait_time,
                ))
        logger().debug("Server has been rebooted")

    def is_server_poweredoff(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredoff"

    def is_server_poweredon(self, server):
        return server.obj.summary.runtime.powerState.lower() == "poweredon"

    def is_server_guest_running(self, server):
        return server.obj.guest.guestState == "running"

    def delete_server(self, server):
        logger().debug("Entering server delete procedure.")
        if self.is_server_poweredon(server):
            self.stop_server(server)
        task = server.obj.Destroy()
        self._wait_for_task(task)
        logger().debug("Server is now deleted.")

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
                             allowed_clusters=None,
                             datacenter=None):
        logger().debug('Finding suitable hosts for deployment.')

        # Find the hosts in the correct datacenter
        if datacenter:
            hosts = self._get_hosts_in_tree(datacenter.obj.hostFolder)
        else:
            hosts = self._get_hosts()

        host_names = [host.name for host in hosts]
        logger().debug(
            'Found hosts: {hosts}'.format(
                hosts=', '.join(host_names),
            )
        )

        if allowed_hosts:
            hosts = [host for host in hosts if host.name in allowed_hosts]
            logger().debug(
                'Filtered list of hosts to be considered: {hosts}'.format(
                    hosts=', '.join([host.name for host in hosts]),
                )
            )

        if allowed_clusters:
            cluster_list = self._get_clusters()
            cluster_names = [cluster.name for cluster in cluster_list]
            valid_clusters = set(allowed_clusters).union(set(cluster_names))
            logger().debug(
                'Only hosts on the following clusters will be used: '
                '{clusters}'.format(
                    clusters=', '.join(valid_clusters),
                )
            )

        candidate_hosts = []
        for host in hosts:
            if not self.host_is_usable(host):
                logger().warn(
                    'Host {host} not usable due to health status.'.format(
                        host=host.name,
                    )
                )
                continue

            if allowed_clusters:
                cluster = self.get_host_cluster_membership(host)
                if cluster not in allowed_clusters:
                    if cluster:
                        logger().warn(
                            'Host {host} is in cluster {cluster}, '
                            'which is not an allowed cluster.'.format(
                                host=host.name,
                                cluster=cluster,
                            )
                        )
                    else:
                        logger().warn(
                            'Host {host} is not in a cluster, '
                            'and allowed clusters have been set.'.format(
                                host=host.name,
                            )
                        )
                    continue

            memory_weight = self.host_memory_usage_ratio(host, vm_memory)

            if memory_weight < 0:
                logger().warn(
                    'Host {host} will not have enough free memory if all VMs '
                    'are powered on.'.format(
                        host=host.name,
                    )
                )

            resource_pools = self.get_host_resource_pools(host)
            resource_pools = [pool.name for pool in resource_pools]
            if resource_pool not in resource_pools:
                logger().warn(
                    'Host {host} does not have resource pool {rp}.'.format(
                        host=host.name,
                        rp=resource_pool,
                    )
                )
                continue

            host_nets = set([
                (
                    self._get_normalised_name(network['name']),
                    network['switch_distributed'],
                )
                for network in self.get_host_networks(host)
            ])
            vm_nets = set([
                (
                    self._get_normalised_name(network['name']),
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

                logger().warn(
                    message.format(
                        host=host.name,
                        nets=missing_standard_nets,
                        dnets=missing_distributed_nets,
                    )
                )
                continue

            logger().debug(
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
            logger().debug(
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

            raise NonRecoverableError(message)

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
        raise NonRecoverableError(
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
        logger().debug('Selecting best host and datastore.')

        best_host = None
        best_datastore = None
        best_datastore_weighting = None

        if allowed_datastores:
            datastore_list = self._get_datastores()
            datastore_names = [datastore.name for datastore in datastore_list]

            valid_datastores = set(allowed_datastores).union(
                set(datastore_names)
            )
            logger().debug(
                'Only the following datastores will be used: '
                '{datastores}'.format(
                    datastores=', '.join(valid_datastores),
                )
            )

        for host in candidate_hosts:
            host = host[0]
            logger().debug('Considering host {host}'.format(host=host.name))

            datastores = host.datastore
            logger().debug(
                'Host {host} has datastores: {ds}'.format(
                    host=host.name,
                    ds=', '.join([ds.name for ds in datastores]),
                )
            )
            if allowed_datastores:
                logger().debug(
                    'Checking only allowed datastores: {allow}'.format(
                        allow=', '.join(allowed_datastores),
                    )
                )

                datastores = [
                    ds for ds in datastores
                    if ds.name in allowed_datastores
                ]

                if len(datastores) == 0:
                    logger().warn(
                        'Host {host} had no allowed datastores.'.format(
                            host=host.name,
                        )
                    )
                    continue

            logger().debug(
                'Filtering for healthy datastores on host {host}'.format(
                    host=host.name,
                )
            )

            healthy_datastores = []
            for datastore in datastores:
                if self.datastore_is_usable(datastore):
                    logger().debug(
                        'Datastore {ds} on host {host} is healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )
                    healthy_datastores.append(datastore)
                else:
                    logger().warn(
                        'Excluding datastore {ds} on host {host} as it is '
                        'not healthy.'.format(
                            ds=datastore.name,
                            host=host.name,
                        )
                    )

            if len(healthy_datastores) == 0:
                logger().warn(
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
                    logger().debug(
                        'Datastore {ds} on host {host} has suitability '
                        '{weight}'.format(
                            ds=datastore.name,
                            weight=weighting,
                            host=host.name,
                        )
                    )
                    candidate_datastores.append((datastore, weighting))
                else:
                    logger().warn(
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
                    logger().debug(
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
            raise NonRecoverableError(message)

    def get_host_free_memory(self, host):
        """
            Get the amount of unallocated memory on a host.
        """
        total_memory = host.hardware.memorySize // 1024 // 1024
        used_memory = 0
        for vm in host.vm:
            if not vm.summary.config.template:
                try:
                    used_memory += int(vm.summary.config.memorySizeMB)
                except StandardError:
                    logger().warning("Incorrect value for memorySizeMB. It is "
                                     "{0} but integer value is expected"
                                     .format(vm.summary.config.memorySizeMB))
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
            try:
                total_assigned += int(vm.summary.config.numCpu)
            except StandardError:
                logger().warning("Incorrect value for numCpu. It is "
                                 "{0} but integer value is expected"
                                 .format(vm.summary.config.numCpu))
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
        if (
            isinstance(host.parent, vim.ClusterComputeResource) or
            isinstance(host.parent.obj, vim.ClusterComputeResource)
        ):
            return host.parent.name
        else:
            return None

    def host_is_usable(self, host):
        """
            Return True if this host is usable for deployments,
            based on its health.
            Return False otherwise.
        """
        healthy_state = host.overallStatus in (
            vim.ManagedEntity.Status.green,
            vim.ManagedEntity.Status.yellow,
        )
        connected = host.summary.runtime.connectionState == 'connected'
        maintenance = host.summary.runtime.inMaintenanceMode

        if healthy_state and connected and not maintenance:
            # TODO: Check license state (will be yellow for bad license)
            return True
        else:
            return False

    def resize_server(self, server, cpus=None, memory=None):
        logger().debug("Entering resize reconfiguration.")
        config = vim.vm.ConfigSpec()
        if cpus is not None:
            try:
                cpus = int(cpus)
            except (ValueError, TypeError) as e:
                raise NonRecoverableError(
                    "Invalid cpus value: {}".format(e))
            if cpus < 1:
                raise NonRecoverableError(
                    "cpus must be at least 1. Is {}".format(cpus))
            config.numCPUs = cpus
        if memory is not None:
            try:
                memory = int(memory)
            except (ValueError, TypeError) as e:
                raise NonRecoverableError(
                    "Invalid memory value: {}".format(e))
            if memory < 512:
                raise NonRecoverableError(
                    "Memory must be at least 512MB. Is {}".format(memory))
            if memory % 128:
                raise NonRecoverableError(
                    "Memory must be an integer multiple of 128. Is {}".format(
                        memory))
            config.memoryMB = memory

        task = server.obj.Reconfigure(spec=config)

        try:
            self._wait_for_task(task)
        except NonRecoverableError as e:
            if 'configSpec.memoryMB' in e.args[0]:
                raise NonRecoverableError(
                    "Memory error resizing Server. May be caused by "
                    "https://kb.vmware.com/kb/2008405 . If so the Server may "
                    "be resized while it is switched off.",
                    e,
                )
            raise

        logger().debug(
            "Server '%s' resized with new number of "
            "CPUs: %s and RAM: %s." % (server.name, cpus, memory))

    def get_server_ip(self, vm, network_name, ignore_local=True):
        logger().debug(
            'Getting server IP from {network}.'.format(
                network=network_name,
            )
        )

        for network in vm.guest.net:
            if not network.network:
                logger().warn(
                    'Ignoring device with MAC {mac} as it is not on a '
                    'vSphere network.'.format(
                        mac=network.macAddress,
                    )
                )
                continue
            if (
                network.network and
                network_name.lower() == self._get_normalised_name(
                    network.network) and
                len(network.ipAddress) > 0
            ):
                ip_address = get_ip_from_vsphere_nic_ips(network, ignore_local)
                # This should be debug, but left as info until CFY-4867 makes
                # logs more visible
                logger().info(
                    'Found {ip} from device with MAC {mac}'.format(
                        ip=ip_address,
                        mac=network.macAddress,
                    )
                )
                return ip_address

    def _task_guest_state_is_running(self, task):
        try:
            logger().debug("VM state: {state}"
                           .format(state=task.info.result.guest.guestState))
            return task.info.result.guest.guestState == "running"
        except vmodl.fault.ManagedObjectNotFound:
            raise NonRecoverableError(
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

    def _wait_vm_running(self, task, adaptermaps, other=False):
        # wait for task finish
        self._wait_for_task(task)

        # check VM state
        while not self._task_guest_state_is_running(task):
            time.sleep(TASK_CHECK_SLEEP)

        # skip guests check for other
        if other:
            logger().info("Skip guest checks for other os")
            return

        # check guest networks
        if not self._task_guest_has_networks(task, adaptermaps):
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
        logger().debug("Deleting port group {name}.".format(name=name))
        for host in self.get_host_list():
            host.configManager.networkSystem.RemovePortGroup(name)
        logger().debug("Port group {name} was deleted.".format(name=name))

    def get_vswitches(self):
        logger().debug('Getting list of vswitches')

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

        logger().debug('Found vswitches: {vswitches}'
                       .format(vswitches=vswitches))
        return vswitches

    def get_vswitch_mtu(self, vswitch_name):
        mtu = -1

        for host in self._get_hosts():
            conf = host.config
            for vswitch in conf.network.vswitch:
                if vswitch_name == vswitch.name:
                    if mtu == -1:
                        mtu = vswitch.mtu
                    elif mtu > vswitch.mtu:
                        mtu = vswitch.mtu
        return mtu

    def get_dvswitches(self):
        logger().debug('Getting list of dvswitches')

        # This does not currently address multiple datacenters (indeed,
        # much of this code will probably have issues in such an environment).
        dvswitches = self._get_dvswitches()
        dvswitches = [dvswitch.name for dvswitch in dvswitches]

        logger().debug('Found dvswitches: {dvswitches}'
                       .format(dvswitches=dvswitches))
        return dvswitches

    def create_port_group(self, port_group_name, vlan_id, vswitch_name):
        logger().debug("Entering create port procedure.")
        runtime_properties = ctx.instance.runtime_properties
        if NETWORK_STATUS not in runtime_properties.keys():
            runtime_properties[NETWORK_STATUS] = 'preparing'

        vswitches = self.get_vswitches()

        if runtime_properties[NETWORK_STATUS] == 'preparing':
            if vswitch_name not in vswitches:
                if len(vswitches) == 0:
                    raise NonRecoverableError(
                        'No valid vswitches found. '
                        'Every physical host in the datacenter must have the '
                        'same named vswitches available when not using '
                        'distributed vswitches.'
                    )
                else:
                    raise NonRecoverableError(
                        '{vswitch} was not a valid vswitch name. The valid '
                        'vswitches are: {vswitches}'.format(
                            vswitch=vswitch_name,
                            vswitches=', '.join(vswitches),
                        )
                    )

        # update mtu
        ctx.instance.runtime_properties[NETWORK_MTU] = self.get_vswitch_mtu(
            vswitch_name)

        if runtime_properties[NETWORK_STATUS] in ('preparing', 'creating'):
            runtime_properties[NETWORK_STATUS] = 'creating'
            if NETWORK_CREATE_ON not in runtime_properties.keys():
                runtime_properties[NETWORK_CREATE_ON] = []

            hosts = [
                host for host in self.get_host_list()
                if host.name not in runtime_properties[NETWORK_CREATE_ON]
            ]

            for host in hosts:
                network_system = host.configManager.networkSystem
                specification = vim.host.PortGroup.Specification()
                specification.name = port_group_name
                specification.vlanId = vlan_id
                specification.vswitchName = vswitch_name
                vswitch = network_system.networkConfig.vswitch[0]
                specification.policy = vswitch.spec.policy
                logger().debug(
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
                runtime_properties[NETWORK_CREATE_ON].append(host.name)

            if self.port_group_is_on_all_hosts(port_group_name):
                runtime_properties[NETWORK_STATUS] = 'created'
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

        logger().debug(
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
        logger().debug("Getting port group by name.")
        result = []
        for host in self.get_host_list():
            network_system = host.configManager.networkSystem
            port_groups = network_system.networkInfo.portgroup
            for port_group in port_groups:
                if name.lower() == port_group.spec.name.lower():
                    logger().debug(
                        "Port group(s) info: \n%s." % "".join(
                            "%s: %s" % item
                            for item in
                            vars(port_group).items()))
                    result.append(port_group)
        return result

    def create_dv_port_group(self, port_group_name, vlan_id, vswitch_name):
        logger().debug("Creating dv port group.")

        dvswitches = self.get_dvswitches()

        if vswitch_name not in dvswitches:
            if len(dvswitches) == 0:
                raise NonRecoverableError(
                    'No valid dvswitches found. '
                    'A distributed virtual switch must exist for distributed '
                    'port groups to be used.'
                )
            else:
                raise NonRecoverableError(
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
        logger().debug("Distributed vSwitch info: {dvswitch}"
                       .format(dvswitch=dvswitch))
        # update mtu
        dvswitch = self._get_obj_by_name(
            vim.DistributedVirtualSwitch,
            vswitch_name,
        )
        ctx.instance.runtime_properties[
            NETWORK_MTU] = dvswitch.obj.config.maxMtu
        vlan_spec = vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(
            vlanId=vlan_id)
        port_settings = \
            vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
                vlan=vlan_spec)
        specification = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(
            name=port_group_name,
            defaultPortConfig=port_settings,
            type=dv_port_group_type)
        logger().debug(
            'Adding distributed port group {group_name} to dvSwitch '
            '{dvswitch_name}'.format(
                group_name=port_group_name,
                dvswitch_name=vswitch_name,
            )
        )
        task = dvswitch.obj.AddPortgroup(specification)
        self._wait_for_task(task)
        logger().debug("Port created.")

    def delete_dv_port_group(self, name):
        logger().debug("Deleting dv port group {name}.".format(name=name))
        dv_port_group = self._get_obj_by_name(
            vim.dvs.DistributedVirtualPortgroup,
            name,
        )
        task = dv_port_group.obj.Destroy()
        self._wait_for_task(task)
        logger().debug("Port deleted.")

    def get_network_cidr(self, name, switch_distributed):
        # search in all datacenters
        for dc in self.si.content.rootFolder.childEntity:
            # select all ipppols
            pools = self.si.content.ipPoolManager.QueryIpPools(dc=dc)
            for pool in pools:
                # check network associations pools
                for association in pool.networkAssociation:
                    # check network type
                    network_distributed = isinstance(
                        association.network,
                        vim.dvs.DistributedVirtualPortgroup)
                    if (
                        association.networkName == name and
                        network_distributed == switch_distributed
                    ):
                        # convert network information to CIDR
                        return str(netaddr.IPNetwork(
                            '{network}/{netmask}'
                            .format(network=pool.ipv4Config.subnetAddress,
                                    netmask=pool.ipv4Config.netmask)))
        # We dont have any ipppols related to network
        return "0.0.0.0/0"

    def get_network_mtu(self, name, switch_distributed):
        if switch_distributed:
            # select virtual port group
            dv_port_group = self._get_obj_by_name(
                vim.dvs.DistributedVirtualPortgroup,
                name,
            )
            if not dv_port_group:
                raise NonRecoverableError(
                    "Unable to get DistributedVirtualPortgroup: {name}"
                    .format(name=repr(name)))
            # get assigned VirtualSwith
            dvSwitch = dv_port_group.config.distributedVirtualSwitch
            return dvSwitch.obj.config.maxMtu
        else:
            mtu = -1
            # search hosts with vswitches
            hosts = self.get_host_list()
            for host in hosts:
                conf = host.config
                # iterate by vswitches
                for vswitch in conf.network.vswitch:
                    # search port group in linked
                    port_name = "key-vim.host.PortGroup-{name}".format(
                        name=name)
                    # check that we have linked network in portgroup(str list)
                    if port_name in vswitch.portgroup:
                        # use mtu from switch
                        if mtu == -1:
                            mtu = vswitch.mtu
                        elif mtu > vswitch.mtu:
                            mtu = vswitch.mtu
            return mtu

    def create_ippool(self, datacenter_name, ippool, networks):
        # create ip pool only on specific datacenter
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=repr(datacenter_name)))
        pool = vim.vApp.IpPool(name=ippool['name'])
        pool.ipv4Config = vim.vApp.IpPool.IpPoolConfigInfo()
        pool.ipv4Config.subnetAddress = ippool['subnet']
        pool.ipv4Config.netmask = ippool['netmask']
        pool.ipv4Config.gateway = ippool['gateway']
        pool.ipv4Config.range = ippool['range']
        pool.ipv4Config.dhcpServerAvailable = ippool.get('dhcp', False)
        pool.ipv4Config.ipPoolEnabled = ippool.get('enabled', True)
        # add networks to pool
        for network in networks:
            network_name = network.runtime_properties["network_name"]
            logger().debug("Attach network {network} to {pool}."
                           .format(network=network_name, pool=ippool['name']))
            if network.runtime_properties.get("switch_distributed"):
                # search vim.dvs.DistributedVirtualPortgroup
                dv_port_group = self._get_obj_by_name(
                    vim.dvs.DistributedVirtualPortgroup,
                    network_name,
                )
                pool.networkAssociation.insert(0, vim.vApp.IpPool.Association(
                    network=dv_port_group.obj))
            else:
                # search all networks
                networks = [
                    net for net in self._collect_properties(
                        vim.Network, path_set=["name"],
                    ) if not net['obj']._moId.startswith('dvportgroup')]
                # attach all networks with provided name
                for net in networks:
                    if net[VSPHERE_RESOURCE_NAME] == network_name:
                        pool.networkAssociation.insert(
                            0, vim.vApp.IpPool.Association(network=net['obj']))
        return self.si.content.ipPoolManager.CreateIpPool(dc=dc.obj, pool=pool)

    def delete_ippool(self, datacenter_name, ippool_id):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=repr(datacenter_name)))
        self.si.content.ipPoolManager.DestroyIpPool(dc=dc.obj, id=ippool_id,
                                                    force=True)


class RawVolumeClient(VsphereClient):

    def delete_file(self, datacenter_name, datastorepath):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=repr(datacenter_name)))
        self.si.content.fileManager.DeleteFile(datastorepath, dc.obj)

    def upload_file(self, datacenter_name, allowed_datastores,
                    allowed_datastore_ids, remote_file, data, host,
                    port):
        dc = self._get_obj_by_name(vim.Datacenter, datacenter_name)
        if not dc:
            raise NonRecoverableError(
                "Unable to get datacenter: {datacenter}"
                .format(datacenter=repr(datacenter_name)))
        ctx.logger.debug(
            "Will check storage with IDs: {ids}; and names: {names}"
            .format(ids=repr(allowed_datastore_ids),
                    names=repr(allowed_datastores)))

        datastores = self._get_datastores()
        ds = None
        if not allowed_datastores and not allowed_datastore_ids and datastores:
            ds = datastores[0]
        else:
            # select by datastore ids
            if allowed_datastore_ids:
                for datastore in datastores:
                    if datastore.id in allowed_datastore_ids:
                        ds = datastore
                        break
            # select by datastore names
            if not ds and allowed_datastores:
                for datastore in datastores:
                    if datastore.name in allowed_datastores:
                        ds = datastore
                        break
        if not ds:
            raise NonRecoverableError(
                "Unable to get datastore {allowed} in {available}"
                .format(allowed=repr(allowed_datastores),
                        available=repr([datastore.name
                                        for datastore in datastores])))

        params = {"dsName": ds.name,
                  "dcPath": dc.name}
        http_url = (
            "https://" + host + ":" + str(port) + "/folder/" + remote_file
        )

        # Get the cookie built from the current session
        client_cookie = self.si._stub.cookie
        # Break apart the cookie into it's component parts - This is more than
        # is needed, but a good example of how to break apart the cookie
        # anyways. The verbosity makes it clear what is happening.
        cookie_name = client_cookie.split("=", 1)[0]
        cookie_value = client_cookie.split("=", 1)[1].split(";", 1)[0]
        cookie_path = client_cookie.split("=", 1)[1].split(";", 1)[1].split(
            ";", 1)[0].lstrip()
        cookie_text = " " + cookie_value + "; $" + cookie_path
        # Make a cookie
        cookie = dict()
        cookie[cookie_name] = cookie_text

        response = requests.put(
            http_url,
            params=params,
            data=data,
            headers={'Content-Type': 'application/octet-stream'},
            cookies=cookie,
            verify=False)
        response.raise_for_status()
        return "[{datastore}] {file_name}".format(
            datastore=ds.name, file_name=remote_file)


class StorageClient(VsphereClient):

    def create_storage(self, vm_id, storage_size, parent_key, mode,
                       thin_provision=False):
        logger().debug("Entering create storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        logger().debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
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

        virtual_device_spec.device.backing.diskMode = mode
        virtual_device_spec.device.backing.thinProvisioned = thin_provision
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
                p = re.compile('^(\\[.*\\]\\s+.*\\/.*)\\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if vm_disk_filename is None:
                    vm_disk_filename = m.group(1)
                p = re.compile('^(.*)_([0-9]+)\\.vmdk$')
                m = p.match(vm_disk_filename_cur)
                if m:
                    if m.group(2) is not None:
                        increment = int(m.group(2))
                        vm_disk_filename = m.group(1)
                        if increment > vm_disk_filename_increment:
                            vm_disk_filename_increment = increment

        # Exit error if VMDK filename undefined
        if vm_disk_filename is None:
            raise NonRecoverableError(
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
                if parent_key < 0:
                    num_controller += 1
                    controller = vm_device
                else:
                    if parent_key == vm_device.key:
                        num_controller = 1
                        controller = vm_device
                        break
        if num_controller != 1:
            raise NonRecoverableError(
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
            raise NonRecoverableError(
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
        logger().debug("Task info: \n%s." % prepare_for_log(vars(task)))
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
            raise NonRecoverableError(
                'Could not find SCSI bus ID for disk with filename: '
                '{file}'.format(file=vm_disk_filename)
            )
        else:
            # Give the SCSI ID in the usual format, e.g. 0:1
            scsi_id = ':'.join((str(bus_id), str(unit)))

        return vm_disk_filename, scsi_id

    def delete_storage(self, vm_id, storage_file_name):
        logger().debug("Entering delete storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        logger().debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
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
            raise NonRecoverableError(
                'Error during trying to delete storage: storage not found')

        virtual_device_spec.device = device_to_delete

        devices.append(virtual_device_spec)

        config_spec = vim.vm.ConfigSpec()
        config_spec.deviceChange = devices

        task = vm.obj.Reconfigure(spec=config_spec)
        logger().debug("Task info: \n%s." % prepare_for_log(vars(task)))
        self._wait_for_task(task)

    def get_storage(self, vm_id, storage_file_name):
        logger().debug("Entering get storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        logger().debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if vm:
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk)\
                        and device.backing.fileName == storage_file_name:
                    logger().debug(
                        "Device info: \n%s." % prepare_for_log(vars(device))
                    )
                    return device
        return None

    def resize_storage(self, vm_id, storage_filename, storage_size):
        logger().debug("Entering resize storage procedure.")
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        logger().debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        if self.is_server_suspended(vm):
            raise NonRecoverableError(
                'Error during trying to resize storage: invalid VM state'
                ' - \'suspended\'')

        disk_to_resize = None
        devices = vm.config.hardware.device
        for device in devices:
            if (isinstance(device, vim.vm.device.VirtualDisk) and
                    device.backing.fileName == storage_filename):
                disk_to_resize = device

        if disk_to_resize is None:
            raise NonRecoverableError(
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
        logger().debug("VM info: \n%s." % prepare_for_log(vars(vm)))
        self._wait_for_task(task)
        logger().debug("Storage resized to a new size %s." % storage_size)


class ControllerClient(VsphereClient):

    def detach_controller(self, vm_id, bus_key):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")
        if not bus_key:
            raise NonRecoverableError("Device Key is not defined")

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)

        config_spec = vim.vm.device.VirtualDeviceSpec()
        config_spec.operation =\
            vim.vm.device.VirtualDeviceSpec.Operation.remove

        for dev in vm.config.hardware.device:
            if hasattr(dev, "key"):
                if dev.key == bus_key:
                    config_spec.device = dev
                    break
        else:
            logger().debug("Controller is not defined {}".format(bus_key))
            return

        spec = vim.vm.ConfigSpec()
        spec.deviceChange = [config_spec]
        task = vm.obj.ReconfigVM_Task(spec=spec)
        self._wait_for_task(task)

    def attach_controller(self, vm_id, dev_spec, controller_type):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)
        known_keys = []
        for dev in vm.config.hardware.device:
            if isinstance(dev, controller_type):
                known_keys.append(dev.key)

        spec = vim.vm.ConfigSpec()
        spec.deviceChange = [dev_spec]
        task = vm.obj.ReconfigVM_Task(spec=spec)
        self._wait_for_task(task)
        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id, use_cache=False)

        controller_properties = {}
        for dev in vm.config.hardware.device:
            if isinstance(dev, controller_type):
                if dev.key not in known_keys:
                    if hasattr(dev, "busNumber"):
                        controller_properties['busNumber'] = dev.busNumber
                    controller_properties['busKey'] = dev.key
                    break
        else:
            raise NonRecoverableError(
                'Have not found key for new added device')
        return controller_properties

    def generate_scsi_card(self, scsi_properties, vm_id):
        if not vm_id:
            raise NonRecoverableError("VM is not defined")

        vm = self._get_obj_by_id(vim.VirtualMachine, vm_id)

        bus_number = scsi_properties.get("busNumber", 0)
        adapter_type = scsi_properties.get('adapterType')
        scsi_controller_label = scsi_properties['label']
        unitNumber = scsi_properties.get("scsiCtlrUnitNumber", -1)
        sharedBus = scsi_properties.get("sharedBus")

        scsi_spec = vim.vm.device.VirtualDeviceSpec()

        if adapter_type == "lsilogic":
            summary = "LSI Logic"
            controller_type = vim.vm.device.VirtualLsiLogicController
        elif adapter_type == "lsilogic_sas":
            summary = "LSI Logic Sas"
            controller_type = vim.vm.device.VirtualLsiLogicSASController
        else:
            summary = "VMware paravirtual SCSI"
            controller_type = vim.vm.device.ParaVirtualSCSIController

        for dev in vm.config.hardware.device:
            if hasattr(dev, "busNumber"):
                if bus_number < dev.busNumber:
                    bus_number = dev.busNumber

        scsi_spec.device = controller_type()
        scsi_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

        scsi_spec.device.busNumber = bus_number
        scsi_spec.device.deviceInfo = vim.Description()
        scsi_spec.device.deviceInfo.label = scsi_controller_label
        scsi_spec.device.deviceInfo.summary = summary

        if int(unitNumber) >= 0:
            scsi_spec.device.scsiCtlrUnitNumber = int(unitNumber)
        if 'hotAddRemove' in scsi_properties:
            scsi_spec.device.hotAddRemove = scsi_properties['hotAddRemove']

        sharingType = vim.vm.device.VirtualSCSIController.Sharing
        if sharedBus == "virtualSharing":
            # Virtual disks can be shared between virtual machines on the
            # same server
            scsi_spec.device.sharedBus = sharingType.virtualSharing
        elif sharedBus == "physicalSharing":
            # Virtual disks can be shared between virtual machines on
            # any server
            scsi_spec.device.sharedBus = sharingType.physicalSharing
        else:
            # Virtual disks cannot be shared between virtual machines
            scsi_spec.device.sharedBus = sharingType.noSharing
        return scsi_spec, controller_type

    def generate_ethernet_card(self, ethernet_card_properties):
        network_name = ethernet_card_properties[VSPHERE_RESOURCE_NAME]
        switch_distributed = ethernet_card_properties.get('switch_distributed')
        adapter_type = ethernet_card_properties.get('adapter_type', "Vmxnet3")
        start_connected = ethernet_card_properties.get('start_connected', True)
        allow_guest_control = ethernet_card_properties.get(
            'allow_guest_control', True)
        network_connected = ethernet_card_properties.get(
            'network_connected', True)
        wake_on_lan_enabled = ethernet_card_properties.get(
            'wake_on_lan_enabled', True)
        address_type = ethernet_card_properties.get('address_type', 'assigned')
        mac_address = ethernet_card_properties.get('mac_address')
        if not network_connected and start_connected:
            logger().debug(
                "Network created unconnected so disable start_connected")
            start_connected = False

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
            raise NonRecoverableError(
                'Network {0} could not be found'.format(network_name))
        nicspec = vim.vm.device.VirtualDeviceSpec()
        # Info level as this is something that was requested in the
        # blueprint
        ctx.logger.info('Adding network interface on {name}'
                        .format(name=network_name))
        nicspec.operation = \
            vim.vm.device.VirtualDeviceSpec.Operation.add

        if adapter_type == "E1000e":
            controller_type = vim.vm.device.VirtualE1000e
        elif adapter_type == "E1000":
            controller_type = vim.vm.device.VirtualE1000
        elif adapter_type == "Sriov":
            controller_type = vim.vm.device.VirtualSriovEthernetCard
        elif adapter_type == "Vmxnet2":
            controller_type = vim.vm.device.VirtualVmxnet2
        else:
            controller_type = vim.vm.device.VirtualVmxnet3

        nicspec.device = controller_type()
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

        nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nicspec.device.connectable.startConnected = start_connected
        nicspec.device.connectable.allowGuestControl = allow_guest_control
        nicspec.device.connectable.connected = network_connected
        nicspec.device.wakeOnLanEnabled = wake_on_lan_enabled
        nicspec.device.addressType = address_type
        if mac_address:
            nicspec.device.macAddress = mac_address
        return nicspec, controller_type


def _with_client(client_name, client):
    def decorator(f):
        @wraps(f)
        def wrapper(connection_config, *args, **kwargs):
            kwargs[client_name] = client().get(config=connection_config)
            if not hasattr(f, '__wrapped__'):
                # don't pass connection_config to the real operation
                kwargs.pop('connection_config', None)

            return f(*args, **kwargs)
        wrapper.__wrapped__ = f
        return wrapper
    return decorator


with_server_client = _with_client('server_client', ServerClient)
with_network_client = _with_client('network_client', NetworkClient)
with_storage_client = _with_client('storage_client', StorageClient)
with_rawvolume_client = _with_client('rawvolume_client', RawVolumeClient)
