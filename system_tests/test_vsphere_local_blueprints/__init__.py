########
# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Stdlib imports
import string

# Third party imports
from pyVim.connect import Disconnect

# Cloudify imports
from cosmo_tester.framework.testenv import (
    initialize_without_bootstrap,
    clear_environment,
)

# This package imports
from vsphere_plugin_common import ServerClient


def setUp():
    initialize_without_bootstrap()


def tearDown():
    clear_environment()


class PlatformCaller(object):
    def __init__(self, host, port, username, password):
        self.cfg = {
            'host': host,
            'username': username,
            'password': password,
            'port': port,
        }
        self.client = None

    def __enter__(self):
        self.client = ServerClient()
        self.client.connect(cfg=self.cfg)
        return self.client

    def __exit__(self, *args):
        Disconnect(self.client.si)


def get_vsphere_vms_list(host, port, username, password):
    with PlatformCaller(host, port, username, password) as client:
        vms = client._get_vms()
    vms = [vm.name.lower() for vm in vms]
    return vms


def get_vsphere_networks(host, port, username, password):
    with PlatformCaller(host, port, username, password) as client:
        nets = client._get_networks()
        nets = [
            {
                'name': net.name,
                'distributed': client._port_group_is_distributed(net),
                'id': net.id,
            }
            for net in nets
        ]
    return nets


def get_vsphere_network_ids_by_name(name, distributed,
                                    host, port, username, password):
    nets = get_vsphere_networks(host, port, username, password)
    nets = [
        net['id'] for net in nets
        if net['name'] == name and
        net['distributed'] == distributed
    ]
    return nets


def check_vm_name_in_runtime_properties(runtime_props, name_prefix, logger,
                                        windows=False):
    logger.info('Checking name is in runtime properties')
    assert 'name' in runtime_props

    name = runtime_props['name']

    check_name_is_correct(name, name_prefix, logger, windows)


def check_correct_vm_name(vms, name_prefix, logger, windows=False):
    # This will fail if there is more than one machine with the same name
    # However, I can't currently see a way to make this cleaner without
    # exporting the vsphere vm name as a runtime property
    this_name_prefix = name_prefix
    candidates = []
    for vm in vms:
        if windows:
            this_name_prefix = get_windows_prefix(
                vm_name=vm,
                name_prefix=name_prefix,
            )
        if vm.startswith(this_name_prefix + '-'):
            candidates.append(vm)

    if len(candidates) > 1:
        raise AssertionError(
            'Too many VMs found with names starting with: '
            '{prefix}-'.format(prefix=name_prefix)
        )
    elif len(candidates) == 0:
        raise AssertionError(
            'Could not find VM with name starting with: {prefix}-'.format(
                prefix=name_prefix,
            )
        )

    vm_name = candidates[0]
    logger.info('Found candidate: {name}'.format(name=vm_name))

    check_name_is_correct(vm_name, name_prefix, logger, windows)


def get_windows_prefix(name_prefix, vm_name, max_windows_name_length=14):
    suffix_length = len(vm_name.split('-')[-1])
    prefix_length = max_windows_name_length - (suffix_length + 1)
    return name_prefix[:prefix_length]


def check_name_is_correct(name, name_prefix, logger, windows=False):
    # Name should be systemte-<id suffix (e.g. abc12)
    if windows:
        name_prefix = get_windows_prefix(
            vm_name=name,
            name_prefix=name_prefix,
        )

    name = name.split('-')
    assert len(name) > 1, (
        'Name is expected to have at least one hyphen, before the instance ID'
    )

    assert '-'.join(name[:-1]) == name_prefix, (
        'Name {prefix} does not match expected {expected}'.format(
            prefix='-'.join(name[:-1]),
            expected=name_prefix,
        )
    )
    logger.info('Candidate has correct name prefix.')

    suffix = name[-1]
    suffix = suffix.strip(string.ascii_letters + string.digits)
    assert suffix == '', 'Suffix contained invalid characters: {}'.format(
        suffix,
    )
    logger.info('Candidate has hex suffix.')
    logger.info('Candidate name appears correct!')


def get_runtime_props(target_node_id, node_instances, logger):
    logger.info('Searching for runtime properties')
    for node in node_instances:
        logger.debug(
            'Considering node {node}'.format(node=node),
        )
        if node['node_id'] == target_node_id:
            logger.info('Found node!')
            return node['runtime_properties']
    raise AssertionError(
        'Could not find node for {node_id} in {nodes}'.format(
            node_id=target_node_id,
            nodes=node_instances,
        )
    )


def network_exists(name, distributed, networks):
    for network in networks:
        if network['name'] == name:
            if network['distributed'] == distributed:
                return True
    raise AssertionError(
        'Failed to find {name} in {networks} where distributed is '
        '{distributed}'.format(
            name=name,
            networks=networks,
            distributed=distributed,
        )
    )


def get_vsphere_entity_id_by_name(name, entity_type,
                                  host, port, username, password):
    with PlatformCaller(host, port, username, password) as client:
        entity = client._get_obj_by_name(
            vimtype=entity_type,
            name=name,
        )
    if entity is not None:
        return entity.id
    else:
        return None
