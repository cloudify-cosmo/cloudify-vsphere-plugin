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

    # Name should be systemte-<id suffix (e.g. abc12)
    vm_name = vm_name.split('-')
    assert len(vm_name) == 2
    logger.info('Candidate name has correct number of hyphens.')

    assert vm_name[0] == name_prefix
    logger.info('Candidate has correct name prefix.')

    # Suffix should be lower case hex
    suffix = vm_name[1]
    suffix = suffix.strip('0123456789abcdef')
    assert suffix == ''
    logger.info('Candidate has hex suffix.')
    logger.info('Candidate name appears correct!')
