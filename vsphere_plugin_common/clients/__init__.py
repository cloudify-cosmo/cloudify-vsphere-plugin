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


from __future__ import division

# Stdlib imports
import os
import ssl
import time
import yaml
import atexit
from copy import copy
from collections import namedtuple
try:
    from collections import MutableMapping
except ImportError:
    from collections.abc import MutableMapping


# Third party imports
from pyVmomi import vim, vmodl
from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError, OperationRetry

# This package imports
from ..constants import (
    NETWORK_ID,
    ASYNC_TASK_ID,
    TASK_CHECK_SLEEP,
    ASYNC_RESOURCE_ID,
    DEFAULT_CONFIG_PATH
)
from .._compat import (
    unquote,
    text_type
)
from ..utils import (
    logger,
)


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
                "Deprecated configuration options were found: {0}".format(
                    "; ".join(warnings)),
            )

        return selected

    def get(self):
        cfg = {}
        config_path = self._find_config_file()
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f.read())
        except IOError:
            logger().warn(
                "Unable to read configuration file {config_path}.".format(
                    config_path=config_path))

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
        raise NonRecoverableError("Unable to unset custom values.")

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

    def __init__(self, ctx_logger=None):
        self.cfg = {}
        self._cache = {}
        self._logger = ctx_logger or logger()

    def get(self, config=None, *_, **__):
        static_config = Config().get()
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
                    'Certificate was not found in {path}.'.format(
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
                if 'unknown error' in text_type(err).lower() or \
                        'no certificate or crl found' in \
                        text_type(err).lower():
                    raise NonRecoverableError(
                        'Could not create SSL context with provided '
                        'certificate {path}. This problem may be caused by '
                        'the certificate not being in the correct format '
                        '(PEM).'.format(path=certificate_path))
                else:
                    raise
        elif not allow_insecure:
            self._logger.warn(
                'DEPRECATED: certificate_path was not supplied. '
                'A certificate will be required in the next major '
                'release of the plugin if allow_insecure is not set '
                'to true.'
            )

        try:
            if allow_insecure:
                self._logger.warn(
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
                'Could not login to vSphere on {host} with provided '
                'credentials'.format(host=host)
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
        keys = set(list(dict1.keys()) + list(dict2.keys()))
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
        name = unquote(name)
        return name.lower() if tolower else name

    def _make_cached_object(self, obj_name, props_dict, platform_results,
                            root_object=True, other_entity_mappings=None):
        just_keys = list(props_dict.keys())
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

                        if map_type == 'static' and \
                                len(mapped) != len(args[mapping]):
                            mapped = None

                    if mapped is None:
                        raise OperationRetry(
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

        if 'name' in args:
            args['name'] = self._get_normalised_name(args['name'], False)

        result = obj(
            **args
        )

        return result

    def _get_entity(self,
                    entity_name,
                    props,
                    vimtype,
                    use_cache=True,
                    other_entity_mappings=None,
                    skip_broken_objects=False):

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
                    )
                )
            except KeyError as err:
                message = (
                    'Could not retrieve all details for {type} object. '
                    '{err} was missing.'.format(
                        type=entity_name,
                        err=text_type(err)
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
                    self._logger.warn(message)
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
            raise OperationRetry(
                'Resource pools changed while getting resource pool details.'
            )

        if 'name' in this_pool:
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
            'name',
            'parent'
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
            use_cache=use_cache
        )

    def _get_connected_network_name(self, network):
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
            return net.name
        else:
            return network['name']

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
            if 'name' in item:
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
            try:
                dvswitch_id = item['config.distributedVirtualSwitch']._moId
            except KeyError:
                ctx.logger.info(
                    'Get extra DV port group details. '
                    'Ignoring item {item}'.format(item=item))
            dvswitch = None
            for dvs in dvswitches:
                if dvswitch_id == dvs.id:
                    dvswitch = dvs
                    break
            if dvswitch is None:
                raise OperationRetry(
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
                    'parent': self._get_clusters(
                        use_cache=use_cache) + self._get_computes(
                        use_cache=use_cache),
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

    def _get_tasks(self, *_, **__):
        task_object = namedtuple(
            'task',
            ['id', 'obj'],
        )

        return [task_object(id=task._moId, obj=task)
                for task in self.si.content.taskManager.recentTask]

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
            vim.Task: self._get_tasks,
            vim.ComputeResource: self._get_computes}.get(vimtype)
        if not getter_method:
            raise NonRecoverableError(
                'Cannot retrieve objects for {vimtype}'.format(
                    vimtype=vimtype))
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

    def _get_entity_datacenter(self, obj):
        if isinstance(obj, vim.Datacenter):
            return obj
        datacenter = None
        while True:
            if not hasattr(obj, 'parent'):
                break
            obj = obj.parent
            if isinstance(obj, vim.Datacenter):
                datacenter = obj
                break
        return datacenter

    def _get_obj_by_name(self, vimtype, name, use_cache=True,
                         datacenter_name=None):

        entities = self._get_getter_method(vimtype)(use_cache)
        name = self._get_normalised_name(name)
        for entity in entities:
            if name == entity.name.lower():
                # check if we are looking inside specific datacenter
                if datacenter_name:
                    # get the entity datacenter via parent property
                    entity_dc = self._get_entity_datacenter(entity)
                    if entity_dc and entity_dc.name == datacenter_name:
                        return entity
                else:
                    return entity

    def _get_obj_by_id(self, vimtype, id, use_cache=True):
        entities = self._get_getter_method(vimtype)(use_cache)
        for entity in entities:
            if entity.id == id:
                return entity

    def _wait_for_task(self,
                       task=None,
                       instance=None,
                       max_wait_time=None,
                       resource_id=None):

        instance = instance or ctx.instance
        if not isinstance(max_wait_time, int):
            ctx.logger.warn(
                'The provided max_wait_time {p} is not an integer. '
                'Using default 300.'.format(p=max_wait_time))
            max_wait_time = 300

        if not task and instance:
            task_id = instance.runtime_properties.get(ASYNC_TASK_ID)
            resource_id = instance.runtime_properties.get(ASYNC_RESOURCE_ID)
            self._logger.info('Check task_id {task_id}'.format(
                task_id=task_id))
            # no saved tasks
            if not task_id:
                return
        else:
            task_id = task._moId
            if instance:
                self._logger.info('Save task_id {task_id}'.format(
                    task_id=task_id))
                instance.runtime_properties[ASYNC_TASK_ID] = task_id
                instance.runtime_properties[ASYNC_RESOURCE_ID] = resource_id
                # save flag as current state before external call
                instance.update()

        if not task:
            task_obj = self._get_obj_by_id(vim.Task, task_id)
            if not task_obj:
                self._logger.info(
                    'No task_id? {task_id}'.format(task_id=task_id))
                if instance:
                    # no such tasks
                    del instance.runtime_properties[ASYNC_TASK_ID]
                    # save flag as current state before external call
                    instance.update()
                return
            task = task_obj.obj

        retry_count = max_wait_time // TASK_CHECK_SLEEP

        while task.info.state in (vim.TaskInfo.State.queued,
                                  vim.TaskInfo.State.running):
            time.sleep(TASK_CHECK_SLEEP)

            self._logger.debug(
                'Task state {state} left {step} seconds'.format(
                    state=task.info.state,
                    step=(retry_count * TASK_CHECK_SLEEP)))
            # check async
            if instance and retry_count <= 0:
                raise OperationRetry(
                    'Task {task_id} is not finished yet.'.format(
                        task_id=task._moId))
            retry_count -= 1

        # we correctly finished, and need to cleanup
        if instance:
            self._logger.info('Cleanup task_id {task_id}'.format(
                task_id=task_id))
            del instance.runtime_properties[ASYNC_TASK_ID]
            del instance.runtime_properties[ASYNC_RESOURCE_ID]
            # save flag as current state before external call
            instance.update()

        if task.info.state != vim.TaskInfo.State.success:
            raise NonRecoverableError(
                "Error during executing task on vSphere: '{0}'".format(
                    task.info.error))
        elif instance and resource_id:
            self._logger.info('Save resource_id {resource_id}'.format(
                resource_id=task.info.result._moId))
            instance.runtime_properties[resource_id] = task.info.result._moId
            # save flag as current state before external call
            instance.update()

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
        self._logger.debug('Getting NIC list.')
        for dev in vm.config.hardware.device:
            if hasattr(dev, 'macAddress'):
                nics.append(dev)

        self._logger.debug('Got NICs: {nics}'.format(nics=nics))
        networks = []
        for nic in nics:
            self._logger.debug('Checking details for NIC {nic}'
                               .format(nic=nic))
            distributed = hasattr(nic.backing, 'port') and isinstance(
                nic.backing.port,
                vim.dvs.PortConnection,
            )
            nsxt_switch = hasattr(nic.backing, 'opaqueNetworkId')

            network_name = None
            if nsxt_switch:
                network_name = nic.backing.opaqueNetworkId
                self._logger.debug(
                    'Found NIC was on port group {network}'.format(
                        network=network_name,
                    )
                )
            elif distributed:
                mapping_id = nic.backing.port.portgroupKey
                self._logger.debug(
                    'Found NIC was on distributed port group with port group '
                    'key {key}'.format(key=mapping_id)
                )
                for network in vm.network:
                    if hasattr(network, 'key'):
                        self._logger.debug(
                            'Checking for match on network with key: '
                            '{key}'.format(key=network.key)
                        )
                        if mapping_id == network.key:
                            network_name = network.name
                            self._logger.debug(
                                'Found NIC was distributed and was on '
                                'network {network}'.format(
                                    network=network_name,
                                )
                            )
            else:
                # If not distributed, the port group name can be retrieved
                # directly
                network_name = nic.backing.deviceName
                self._logger.debug(
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
                'nsxt_switch': nsxt_switch
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
            self._logger.debug('Added custom attributes')
