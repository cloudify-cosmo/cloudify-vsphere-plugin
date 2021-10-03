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

import re

# Third party imports

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError, OperationRetry

# This package imports
from vsphere_plugin_common import with_server_client
from vsphere_plugin_common.clients.server import get_ip_from_vsphere_nic_ips
from vsphere_plugin_common.utils import op, prepare_for_log, find_rels_by_type
from vsphere_plugin_common.constants import (
    IP,
    NETWORKS,
    PUBLIC_IP,
    VSPHERE_SERVER_ID,
    VSPHERE_SERVER_HOST,
    VSPHERE_SERVER_DATASTORE_IDS,
    VSPHERE_SERVER_DATASTORE,
    VSPHERE_SERVER_CONNECTED_NICS,
    VSPHERE_RESOURCE_EXTERNAL,
    VSPHERE_RESOURCE_EXISTING,
)
from vsphere_plugin_common._compat import text_type

RELATIONSHIP_VM_TO_NIC = \
    'cloudify.relationships.vsphere.server_connected_to_nic'


def get_connected_networks(nics_from_props):
    """ Create a list of dictionaries that merges nics specified
    in the VM node properties and those created via relationships.
    :param _ctx: The VMs current context.
    :param nics_from_props: A list of networks
        defined under connect_networks in _networking.
    :return: A list of networks
        defined under connect_networks in _networking.
    """

    if VSPHERE_SERVER_CONNECTED_NICS not in ctx.instance.runtime_properties:
        ctx.instance.runtime_properties[VSPHERE_SERVER_CONNECTED_NICS] = []
    # get all relationship contexts of related nics
    nics_from_rels = find_rels_by_type(ctx.instance, RELATIONSHIP_VM_TO_NIC)
    for rel_nic in nics_from_rels:
        # try to get the connect_network property from the nic.
        _connect_network = rel_nic.target.instance.runtime_properties.get(
            'connected_network')
        if not _connect_network:
            raise NonRecoverableError(
                'No "connect_network" specification for nic {0}.'.format(
                    rel_nic.target.instance.id))
        connected_network_name = _connect_network.get(
            'name',
            rel_nic.target.instance.runtime_properties.get('name'))
        # If it wasn't provided it's not a valid nic.
        if not connected_network_name:
            raise NonRecoverableError(
                'No network name specified for nic {0}.'.format(
                    rel_nic.target.instance.id))
        _connect_network['name'] = connected_network_name

        for prop_nic in nics_from_props:
            # If there is a nic from props that is supposed
            # to use a nic from relationships do so.
            if _connect_network['name'] == prop_nic['name'] and \
                    prop_nic.get('from_relationship'):
                # Merge them.
                prop_nic.update(_connect_network)
                # We can move on to the next nic in the nics_from_props list.
        # Otherwise go head and add it to the list.
        nics_from_props.append(_connect_network)
        ctx.instance.runtime_properties[VSPHERE_SERVER_CONNECTED_NICS].append(
            rel_nic.target.instance.id)
    return nics_from_props


def validate_connect_network(_network):
    """Judges a connected network.

    :param _network: a defendant.
    :return: a valid connected network dictionary.
    """

    # The charges.
    network_validations = {
        'name': (text_type, None),
        'from_relationship': (bool, False),
        'external': (bool, False),
        'management': (bool, False),
        'switch_distributed': (bool, False),
        'nsx_t_switch': (bool, False),
        'use_dhcp': (bool, True),
        'network': (text_type, None),
        'gateway': (text_type, None),
        'ip': (text_type, None)
    }

    # Assumed innocent until proven guilty.
    validation_error = False
    # As proper bureaucrats, we always prepare lists.
    validation_error_messages = ['Network failed validation: ']

    if _network.get('switch_distributed') and _network.get('nsx_t_switch'):
        validation_error = True
        validation_error_messages.append(
            'Cannot specify both switch_distributed & nsx_t_switch at the '
            'same time')
    if not _network.get('name'):
        # John/Jane Doe.
        validation_error = True
        validation_error_messages.append(
            'All networks connected to a server must have a name specified.')
        del network_validations['name']

    # We review each charge as a distinct offense.
    for key, value in list(_network.items()):
        try:
            # We check if the defendant has an alibi.
            expected_type, default_value = network_validations.pop(key)
        except KeyError:
            # The defendant is lying.
            validation_error = True
            validation_error_messages.append(
                'Network has unsupported key: {0}. Value: {1}'.format(
                    key, value))
            continue

        # The defendant was not even at the scene of the crime.
        if not value and expected_type != bool:
            _network[key] = default_value
            continue

        elif not isinstance(_network[key], expected_type):
            # Guilty as charged!
            validation_error = True
            validation_error_messages.append(
                'Network Key {0} has unsupported type: {1}. Value: {2}'.format(
                    key, expected_type, _network[key]))

    if validation_error:
        raise NonRecoverableError(text_type(validation_error_messages))

    # We return the citizen its rights.
    for validation_key, (_, default_value) in network_validations.items():
        _network[validation_key] = default_value

    return _network


def handle_networks(networking_parameters):
    connect_networks = get_connected_networks(
        networking_parameters.get('connect_networks', []))
    ctx.logger.debug(
        'Network properties: {properties} {connect_networks}'.format(
            properties=prepare_for_log(networking_parameters),
            connect_networks=connect_networks
        )
    )
    if connect_networks:
        err_msg = "No more than one %s network can be specified."
        if len([n for n in connect_networks if
                n.get('external', False)]) > 1:
            raise NonRecoverableError(err_msg % 'external')
        if len([n for n in connect_networks if
                n.get('management', False)]) > 1:
            raise NonRecoverableError(err_msg % 'management')

        reordered_networks = []
        for network in connect_networks:
            ctx.logger.info('connected_network: {0}'.format(network))
            validate_connect_network(network)
            if network['external']:
                reordered_networks.insert(0, network)
            else:
                reordered_networks.append(network)
        connect_networks = reordered_networks
    return connect_networks


def validate_vm_name(vm_name, search=re.compile(r'[^A-Za-z0-9\-]').search):
    if bool(search(vm_name)):
        raise NonRecoverableError(
            'Computer name must contain only A-Z, a-z, 0-9, '
            'and hyphens ("-"), and must not consist entirely of '
            'numbers. "{name}" was not valid.'.format(name=vm_name)
        )


def store_server_details(server_client, server_obj):
    ctx.instance.runtime_properties[VSPHERE_SERVER_HOST] = text_type(
        server_obj.summary.runtime.host.name)
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj.id
    ctx.instance.runtime_properties['name'] = server_obj.name
    ctx.instance.runtime_properties[VSPHERE_SERVER_DATASTORE] = [
        datastore.name for datastore in server_obj.datastore]
    ctx.instance.runtime_properties[VSPHERE_SERVER_DATASTORE_IDS] = [
        datastore.id for datastore in server_obj.datastore]
    ctx.instance.runtime_properties[NETWORKS] = \
        server_client.get_vm_networks(server_obj)


def get_vm_name(server, os_family):
    ctx.logger.debug('Server properties: {properties}'.format(
        properties=prepare_for_log(server)))
    # If we've already set the name on this instance, use that.
    vm_name = ctx.instance.runtime_properties.get('name')
    if vm_name is not None:
        return vm_name

    # Gather up the details that we will use to select a name.
    configured_name = server.get('name')
    add_scale_suffix = server.get('add_scale_suffix', True)

    # If we have a configured name and don't want a suffix, we're done.
    if configured_name is not None and not add_scale_suffix:
        return configured_name

    # Prefer to use the configured name as the prefix.
    instance_name, id_suffix = ctx.instance.id.rsplit('_', 1)
    name_prefix = configured_name or instance_name

    # VM name may be at most 15 characters for Windows.
    if os_family.lower() == 'windows':
        max_prefix = 14 - (len(id_suffix) + 1)
        name_prefix = name_prefix[:max_prefix]

    vm_name = '-'.join([name_prefix, id_suffix])

    if '_' in vm_name:
        orig = vm_name
        vm_name = vm_name.replace('_', '-')
        ctx.logger.warn(
            'Changing all _ to - in VM name. Name changed from {orig} to '
            '{new}.'.format(
                orig=orig,
                new=vm_name,
            )
        )
    validate_vm_name(vm_name)
    ctx.logger.info('Creating new server with name: {name}'.format(
        name=vm_name))
    return vm_name


def get_server_by_context(server_client, server, os_family=None):
    ctx.logger.info("Performing look-up for server.")
    if VSPHERE_SERVER_ID in ctx.instance.runtime_properties:
        return server_client.get_server_by_id(
            ctx.instance.runtime_properties[VSPHERE_SERVER_ID])
    elif os_family:
        # Try to get server by name. None will be returned if it is not found
        # This may change in future versions of vmomi
        return server_client.get_server_by_name(
            get_vm_name(server, os_family))

    raise NonRecoverableError(
        'os_family must be provided if the VM might not exist')


def create_new_server(server_client,
                      server,
                      networking,
                      allowed_hosts,
                      allowed_clusters,
                      allowed_datastores,
                      windows_password,
                      windows_organization,
                      windows_timezone,
                      agent_config,
                      custom_sysprep,
                      # Backwards compatibility- only linux was really working
                      os_family='linux',
                      cdrom_image=None,
                      vm_folder=None,
                      extra_config=None,
                      enable_start_vm=True,
                      postpone_delete_networks=False,
                      max_wait_time=300,
                      **_):
    vm_name = get_vm_name(server, os_family)
    ctx.logger.debug('Cdrom path: {cdrom}'.format(cdrom=cdrom_image))

    networks = handle_networks(networking)
    if isinstance(allowed_hosts, text_type):
        allowed_hosts = [allowed_hosts]
    if isinstance(allowed_clusters, text_type):
        allowed_clusters = [allowed_clusters]
    if isinstance(allowed_datastores, text_type):
        allowed_datastores = [allowed_datastores]

    server_obj = server_client.create_server(
        # auto_placement deprecated- deprecation warning emitted where it is
        # actually used.
        auto_placement=server_client.cfg.get('auto_placement', True),
        cpus=server.get('cpus'),
        datacenter_name=server_client.cfg['datacenter_name'],
        memory=server.get('memory'),
        networks=networks,
        resource_pool_name=server_client.cfg['resource_pool_name'],
        template_name=server['template'],
        vm_name=vm_name,
        windows_password=windows_password,
        windows_organization=windows_organization,
        windows_timezone=windows_timezone,
        agent_config=agent_config,
        custom_sysprep=custom_sysprep,
        os_type=os_family,
        domain=networking.get('domain'),
        dns_servers=networking.get('dns_servers'),
        allowed_hosts=allowed_hosts,
        allowed_clusters=allowed_clusters,
        allowed_datastores=allowed_datastores,
        cdrom_image=cdrom_image,
        vm_folder=vm_folder,
        extra_config=extra_config,
        enable_start_vm=enable_start_vm,
        postpone_delete_networks=postpone_delete_networks,
        max_wait_time=max_wait_time,
        retry=ctx.operation.retry_number > 0)
    ctx.logger.info('Created server called {name}'.format(name=vm_name))
    return server_obj


@op
@with_server_client
def create(server_client,
           server,
           networking,
           allowed_hosts,
           allowed_clusters,
           allowed_datastores,
           os_family,
           windows_password,
           windows_organization,
           windows_timezone,
           agent_config,
           custom_sysprep,
           custom_attributes,
           use_external_resource,
           enable_start_vm=False,
           minimal_vm_version=13,
           postpone_delete_networks=False,
           cdrom_image=None,
           vm_folder=None,
           extra_config=None,
           max_wait_time=300,
           **_):
    if enable_start_vm:
        ctx.logger.debug('Create operation ignores enable_start_vm property.')
        enable_start_vm = False

    ctx.logger.debug("Checking whether server exists...")
    if use_external_resource and "name" in server:
        server_obj = server_client.get_server_by_name(server.get('name'))
        if not server_obj:
            raise NonRecoverableError(
                'A VM with name {0} was not found.'.format(server.get('name')))
        ctx.instance.runtime_properties[VSPHERE_RESOURCE_EXISTING] = True
        ctx.instance.runtime_properties[VSPHERE_RESOURCE_EXTERNAL] = True
    elif "template" not in server:
        raise NonRecoverableError('No template provided.')
    else:
        server_obj = get_server_by_context(server_client, server, os_family)

    if not server_obj:
        ctx.logger.info("Server does not exist, creating from scratch.")
        server_obj = create_new_server(
            server_client,
            server,
            networking,
            allowed_hosts,
            allowed_clusters,
            allowed_datastores,
            windows_password,
            windows_organization,
            windows_timezone,
            agent_config,
            custom_sysprep,
            os_family=os_family,
            cdrom_image=cdrom_image,
            vm_folder=vm_folder,
            extra_config=extra_config,
            enable_start_vm=enable_start_vm,
            postpone_delete_networks=postpone_delete_networks,
            max_wait_time=max_wait_time)

    server_client.add_custom_values(server_obj, custom_attributes or {})

    # update vm version
    server_client.upgrade_server(server_obj,
                                 minimal_vm_version=minimal_vm_version)

    # remove nic's by mac
    keys_for_remove = ctx.instance.runtime_properties.get('_keys_for_remove')
    if keys_for_remove:
        ctx.logger.info("Remove devices: {keys}".format(keys=keys_for_remove))
        server_client.remove_nic_keys(server_obj, keys_for_remove)
        del ctx.instance.runtime_properties['_keys_for_remove']
        ctx.instance.runtime_properties.dirty = True
        ctx.instance.update()
    store_server_details(server_client, server_obj)
    ctx.instance.runtime_properties.dirty = True
    ctx.instance.update()


@op
@with_server_client
def start(server_client,
          server,
          networking,
          allowed_hosts,
          allowed_clusters,
          allowed_datastores,
          os_family,
          windows_password,
          windows_organization,
          windows_timezone,
          agent_config,
          custom_sysprep,
          custom_attributes,
          use_external_resource,
          enable_start_vm=True,
          minimal_vm_version=13,
          postpone_delete_networks=False,
          cdrom_image=None,
          vm_folder=None,
          extra_config=None,
          max_wait_time=300,
          **_):
    ctx.logger.debug("Checking whether server exists...")
    if use_external_resource and "name" in server:
        server_obj = server_client.get_server_by_name(server.get('name'))
        if not server_obj:
            raise NonRecoverableError(
                'A VM with name {0} was not found.'.format(server.get('name')))
        ctx.instance.runtime_properties[VSPHERE_RESOURCE_EXISTING] = True
        ctx.instance.runtime_properties[VSPHERE_RESOURCE_EXTERNAL] = True
    elif "template" not in server:
        raise NonRecoverableError('No template provided.')
    else:
        server_obj = get_server_by_context(server_client, server, os_family)

    if not server_obj:
        ctx.logger.info("Server does not exist, creating from scratch.")
        server_obj = create_new_server(
            server_client,
            server,
            networking,
            allowed_hosts,
            allowed_clusters,
            allowed_datastores,
            windows_password,
            windows_organization,
            windows_timezone,
            agent_config,
            custom_sysprep,
            os_family=os_family,
            cdrom_image=cdrom_image,
            vm_folder=vm_folder,
            extra_config=extra_config,
            enable_start_vm=enable_start_vm,
            postpone_delete_networks=postpone_delete_networks,
            max_wait_time=max_wait_time)
    else:
        server_client.update_server(server=server_obj,
                                    cdrom_image=cdrom_image,
                                    extra_config=extra_config,
                                    max_wait_time=max_wait_time)
        if enable_start_vm:
            ctx.logger.info("Server already exists, powering on.")
            server_client.start_server(server=server_obj,
                                       max_wait_time=max_wait_time)
            ctx.logger.info("Server powered on.")
        else:
            ctx.logger.info("Server already exists, but will not be powered"
                            "on as enable_start_vm is set to false")
    _start(server_client,
           server_obj,
           custom_attributes,
           max_wait_time,
           minimal_vm_version)


def _start(server_client,
           server_obj,
           custom_attributes,
           max_wait_time,
           minimal_vm_version):
    server_client.add_custom_values(server_obj, custom_attributes or {})

    # update vm version
    server_client.upgrade_server(server_obj,
                                 minimal_vm_version=minimal_vm_version,
                                 max_wait_time=max_wait_time)

    # remove nic's by mac
    keys_for_remove = ctx.instance.runtime_properties.get('_keys_for_remove')
    if keys_for_remove:
        ctx.logger.info("Remove devices: {keys}".format(keys=keys_for_remove))
        server_client.remove_nic_keys(server_obj, keys_for_remove)
        del ctx.instance.runtime_properties['_keys_for_remove']
        ctx.instance.runtime_properties.dirty = True
        ctx.instance.update()
    store_server_details(server_client, server_obj)
    ctx.instance.runtime_properties.dirty = True
    ctx.instance.update()


@op
@with_server_client
def shutdown_guest(server_client,
                   server,
                   os_family,
                   max_wait_time=300,
                   **_):
    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to shut down server {name}'.format(
        name=vm_name))
    server_client.shutdown_server_guest(server_obj,
                                        max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully shut down server {name}'.format(
        name=vm_name))


@op
@with_server_client
def stop(server_client,
         server,
         os_family,
         force_stop=False,
         max_wait_time=300,
         **_):
    existing_resource = ctx.instance.runtime_properties.get(
        VSPHERE_RESOURCE_EXTERNAL)
    if existing_resource and not force_stop:
        ctx.logger.warn('Not stopping because use_external_resource '
                        'is True and force_stop is False.')
        return
    elif force_stop:
        ctx.logger.warn('The parameter force_stop is True.')

    _stop(server_client, server, os_family, max_wait_time)


def _stop(server_client, server, os_family, max_wait_time):
    server_obj = get_server_by_context(server_client, server, os_family)

    if not server_obj:
        if ctx.instance.runtime_properties.get(VSPHERE_SERVER_ID):
            # skip already deleted host
            raise NonRecoverableError(
                "Cannot stop server - "
                "server doesn't exist for node: {0}".format(ctx.instance.id))
        return

    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Stopping server {name}'.format(name=vm_name))
    server_client.stop_server(server_obj, max_wait_time=max_wait_time)
    ctx.logger.info('Sttopped server {name}'.format(name=vm_name))


@op
@with_server_client
def freeze_suspend(server_client,
                   server,
                   os_family,
                   max_wait_time=300,
                   **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(server_client, server, os_family)
    if not server_obj:
        raise NonRecoverableError(
            "Cannot suspend server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to suspend server {name}'.format(name=vm_name))
    server_client.suspend_server(server_obj, max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully suspended server {name}'.format(
        name=vm_name))


@op
@with_server_client
def freeze_resume(server_client,
                  server,
                  os_family,
                  max_wait_time=300,
                  **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resume server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to resume server {name}'.format(name=vm_name))
    server_client.start_server(server_obj, max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully resumed server {name}'.format(name=vm_name))


@op
@with_server_client
def snapshot_create(server_client,
                    server,
                    os_family,
                    snapshot_name,
                    snapshot_incremental,
                    snapshot_type,
                    max_wait_time=300,
                    **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL):
        ctx.logger.info('Used existing resource.')
        return
    if not snapshot_name:
        raise NonRecoverableError(
            'Backup name must be provided.'
        )
    if not snapshot_incremental:
        # we need to support such flag for interoperability with the
        # utilities plugin
        ctx.logger.info("Create backup for VM is unsupported.")
        return

    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot backup server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to backup {snapshot_name} for server {name}'
                    .format(snapshot_name=snapshot_name, name=vm_name))
    server_client.backup_server(
        server_obj,
        snapshot_name,
        snapshot_type,
        max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully backuped server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def snapshot_apply(server_client,
                   server,
                   os_family,
                   snapshot_name,
                   snapshot_incremental,
                   max_wait_time=300,
                   **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL):
        ctx.logger.info('Used existing resource.')
        return
    if not snapshot_name:
        raise NonRecoverableError(
            'Backup name must be provided.'
        )
    if not snapshot_incremental:
        # we need to support such flag for interoperability with the
        # utilities plugin
        ctx.logger.info("Restore from backup for VM is unsupported.")
        return

    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot restore server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to restore {snapshot_name} for server {name}'
                    .format(snapshot_name=snapshot_name, name=vm_name))
    server_client.restore_server(server_obj,
                                 snapshot_name,
                                 max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully restored server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def snapshot_delete(server_client,
                    server,
                    os_family,
                    snapshot_name,
                    snapshot_incremental,
                    max_wait_time=300,
                    **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL):
        ctx.logger.info('Used existing resource.')
        return
    if not snapshot_name:
        raise NonRecoverableError(
            'Backup name must be provided.'
        )
    if not snapshot_incremental:
        # we need to support such flag for interoperability with the
        # utilities plugin
        ctx.logger.info("Delete backup for VM is unsupported.")
        return

    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot remove backup for server - server doesn't exist for "
            "node: {0}".format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to remove backup {snapshot_name} for server '
                    '{name}'.format(snapshot_name=snapshot_name, name=vm_name))
    server_client.remove_backup(
        server_obj,
        snapshot_name,
        max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully removed backup from server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def delete(server_client,
           server,
           os_family,
           force_delete,
           max_wait_time=300,
           **_):
    if ctx.instance.runtime_properties.get(VSPHERE_RESOURCE_EXTERNAL) \
            and not force_delete:
        ctx.logger.info('Used existing resource.')
        return
    elif force_delete:
        ctx.logger.info('Delete is forced.')
    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        if ctx.instance.runtime_properties.get(VSPHERE_SERVER_ID):
            # skip already deleted host
            ctx.logger.info(
                "Cannot delete server - server doesn't exist for node: {0}"
                .format(ctx.instance.id))
        return
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Preparing to delete server {name}'.format(name=vm_name))
    server_client.delete_server(server_obj, max_wait_time=max_wait_time)
    ctx.logger.info('Succeessfully deleted server {name}'.format(
        name=vm_name))


@op
@with_server_client
def get_state(server_client,
              server,
              networking,
              os_family,
              wait_ip,
              **_):
    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot get info - server doesn't exist for node: {0}".format(
                ctx.instance.id,
            )
        )
    vm_name = get_vm_name(server, os_family)
    ctx.logger.info('Getting state for server {name} ({os_family})'
                    .format(name=vm_name, os_family=os_family))

    if os_family == "other":
        ctx.logger.info("Skip guest checks for other os: {info}"
                        .format(info=text_type(server_obj.guest)))
        return True

    nets = ctx.instance.runtime_properties[NETWORKS]
    if server_client.is_server_guest_running(server_obj):
        ctx.logger.info("Server is running, getting network details.")
        ctx.logger.info("Guest info: {info}"
                        .format(info=text_type(server_obj.guest)))

        networks = networking.get('connect_networks', []) if networking else []
        manager_network_ip = None
        management_networks = \
            [network['name'] for network
             in networking.get('connect_networks', [])
             if network.get('management', False)]
        management_network_name = (management_networks[0]
                                   if len(management_networks) == 1
                                   else None)
        ctx.logger.info("Server management networks: {networks}"
                        .format(networks=text_type(management_networks)))

        # used for guest ip checks
        default_ip = None
        # We must obtain IPs at this stage, as they are not populated until
        # after the VM is fully booted
        for network in server_obj.guest.net:
            network_name = network.network
            # save ip as default
            if not default_ip:
                default_ip = get_ip_from_vsphere_nic_ips(network)
            # check management
            if management_network_name and \
                    (network_name == management_network_name):
                manager_network_ip = get_ip_from_vsphere_nic_ips(network)
                # This should be debug, but left as info until CFY-4867 makes
                # logs more visible
                ctx.logger.info("Server management ip address: {0}"
                                .format(manager_network_ip))
                if manager_network_ip is None:
                    ctx.logger.info(
                        'Manager network IP not yet present for {server}. '
                        'Retrying.'.format(server=server_obj.name)
                    )
                    # This should all be handled in the create server logic
                    # and use operation retries, but until that is implemented
                    # this will have to remain.
                    return False
            for net in nets:
                if net['name'] == network_name:
                    net[IP] = get_ip_from_vsphere_nic_ips(network)

        # if we have some managment network but no ip in such by some reason
        # go and run one more time
        if management_network_name and not manager_network_ip:
            raise OperationRetry("Management IP addresses not yet assigned.")

        ctx.instance.runtime_properties[NETWORKS] = nets
        ctx.instance.runtime_properties[IP] = manager_network_ip or default_ip
        if not ctx.instance.runtime_properties[IP]:
            ctx.logger.warn("Server has no IP addresses.")
            # wait for any ip before next steps
            if wait_ip:
                ctx.logger.info("Waiting ip export from guest.")
                return False

        if len(server_obj.guest.net):
            public_ips = [
                server_client.get_server_ip(server_obj, network['name'])
                for network in networks
                if network.get('external', False)]

            if not public_ips:
                ctx.logger.info("No Server public IP addresses.")
            elif None in public_ips:
                raise OperationRetry("Public IP addresses not yet assigned.")
            else:
                ctx.logger.info("Server public IP addresses: {ips}.".format(
                    ips=text_type(public_ips)))
        else:
            public_ips = []

        # I am uncertain if the logic here is correct, but as this should be
        # refactored to use the more up to date retry logic it's likely not
        # worth a great deal of attention
        if len(public_ips):
            ctx.logger.debug("Public IP address for {name}: {ip}"
                             .format(name=vm_name, ip=public_ips[0]))
            ctx.instance.runtime_properties[PUBLIC_IP] = public_ips[0]
        else:
            ctx.logger.debug('Public IP check not required for {server}'
                             .format(server=server_obj.name))
            # Ensure the property still exists
            ctx.instance.runtime_properties[PUBLIC_IP] = None

        message = 'Server {name} has started'
        if manager_network_ip:
            message += ' with management IP {mgmt}'
        if len(public_ips):
            public_ip = public_ips[0]
            if manager_network_ip:
                message += ' and'
            message += ' public IP {public}'
        else:
            public_ip = ctx.instance.runtime_properties[IP]
        message += '.'

        ctx.logger.info(
            message.format(
                name=vm_name,
                mgmt=manager_network_ip,
                public=public_ip,
            )
        )
        return True
    ctx.logger.info('Server {server} is not started yet'.format(
        server=server_obj.name))
    # This should all be handled in the create server logic and use operation
    # retries, but until that is implemented this will have to remain.
    return False


@op
@with_server_client
def resize_server(server_client,
                  server,
                  os_family,
                  custom_attributes,
                  cpus=None,
                  memory=None,
                  minimal_vm_version=13,
                  max_wait_time=300,
                  hot_add=True,
                  **_):
    ctx.logger.info('{}'.format((server_client,
                                 server,
                                 os_family,
                                 custom_attributes,
                                 cpus,
                                 memory,
                                 minimal_vm_version,
                                 max_wait_time,
                                 hot_add,
                                 _)))

    if not any((cpus, memory,)):
        ctx.logger.info("Attempt to resize Server with no sizes specified")
        return

    if not isinstance(hot_add, bool):
        if hot_add == 'true' or hot_add == 'True':
            hot_add = True
        elif hot_add == 'false' or hot_add == 'False':
            hot_add = False
    else:
        raise NonRecoverableError(
            "The value for parameter hot_add must be a boolean"
            "and is {}".format(type(hot_add)))

    if not hot_add:
        _stop(server_client, server, os_family, max_wait_time)
        ctx.logger.info('Not hot add, so calling server stop.')

    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resize server - "
            "server doesn't exist for node: {0}".format(ctx.instance.id))

    server_client.resize_server(server_obj,
                                cpus=cpus,
                                memory=memory,
                                max_wait_time=max_wait_time)

    for property in 'cpus', 'memory':
        value = locals()[property]
        if value:
            ctx.instance.runtime_properties[property] = value

    if not hot_add:
        _start(server_client,
               server_obj,
               custom_attributes,
               max_wait_time,
               minimal_vm_version)
        ctx.logger.info('Not hot add so calling server start.')


@op
@with_server_client
def resize(server_client, server, os_family, **_):
    ctx.logger.warn(
        "This operation may be removed at any point from "
        "cloudify-vsphere-plugin==3. "
        "Please use resize_server (cloudify.interfaces.modify.resize) "
        "instead.",
    )
    server_obj = get_server_by_context(server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resize server - "
            "server doesn't exist for node: {0}".format(ctx.instance.id))
    vm_name = get_vm_name(server, os_family)

    update = {
        'cpus': ctx.instance.runtime_properties.get('cpus'),
        'memory': ctx.instance.runtime_properties.get('memory')
    }

    if any(update.values()):
        ctx.logger.info(
            "Preparing to resize server {name}, with cpus: {cpus}, and "
            "memory: {memory}".format(
                name=vm_name,
                cpus=update['cpus'] or 'no changes',
                memory=update['memory'] or 'no changes',
            )
        )
        server_client.resize_server(server_obj, **update)
        ctx.logger.info('Succeeded resizing server {name}.'
                        .format(name=vm_name))
    else:
        raise NonRecoverableError(
            "Server resize parameters should be specified.")
