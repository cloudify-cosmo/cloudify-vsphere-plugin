########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

from cosmo_tester.framework.testenv import (initialize_without_bootstrap,
                                            clear_environment)
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect

import string


def setUp():
    initialize_without_bootstrap()


def tearDown():
    clear_environment()


def get_vsphere_vms_list(host, port, username, password):
    vsphere_conn = SmartConnect(
        user=username,
        pwd=password,
        host=host,
        port=port,
    )
    vsphere_content = vsphere_conn.RetrieveContent()
    vsphere_container = vsphere_content.viewManager.CreateContainerView(
        vsphere_content.rootFolder,
        [vim.VirtualMachine],
        True,
    )
    vms = vsphere_container.view
    vsphere_container.Destroy()
    vms = [vm.name.lower() for vm in vms]
    Disconnect(vsphere_conn)
    return vms


def get_vsphere_networks(host, port, username, password):
    vsphere_conn = SmartConnect(
        user=username,
        pwd=password,
        host=host,
        port=port,
    )
    vsphere_content = vsphere_conn.RetrieveContent()
    vsphere_container = vsphere_content.viewManager.CreateContainerView(
        vsphere_content.rootFolder,
        [vim.Network],
        True,
    )
    nets = vsphere_container.view
    vsphere_container.Destroy()
    nets = [
        {
            'name': net.name,
            'distributed': is_distributed(net),
        }
        for net in nets
    ]
    Disconnect(vsphere_conn)
    return nets


def check_vm_name_in_runtime_properties(runtime_props, name_prefix, logger):
    logger.info('Checking name is in runtime properties')
    assert 'name' in runtime_props

    name = runtime_props['name']

    check_name_is_correct(name, name_prefix, logger)


def check_correct_vm_name(vms, name_prefix, logger):
    # This will fail if there is more than one machine with the same name
    # However, I can't currently see a way to make this cleaner without
    # exporting the vsphere vm name as a runtime property
    candidates = []
    for vm in vms:
        if vm.startswith(name_prefix + '-'):
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

    check_name_is_correct(vm_name, name_prefix, logger)


def check_name_is_correct(name, name_prefix, logger):
    # Name should be systemte-<id suffix (e.g. abc12)
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


def is_distributed(network):
    if isinstance(network, vim.dvs.DistributedVirtualPortgroup):
        return True
    else:
        return False


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
