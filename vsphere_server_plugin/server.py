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

# Stdlib imports
import string

# Third party imports

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from cloudify_vsphere.utils import op, find_rels_by_type
from cloudify_vsphere.utils.feedback import prepare_for_log
from vsphere_plugin_common import (
    get_ip_from_vsphere_nic_ips,
    remove_runtime_properties,
    with_server_client,
)
from vsphere_plugin_common.constants import (
    IP,
    NETWORKS,
    PUBLIC_IP,
    SERVER_RUNTIME_PROPERTIES,
    VSPHERE_SERVER_ID,
    VSPHERE_SERVER_HOST,
    VSPHERE_SERVER_DATASTORE_IDS,
    VSPHERE_SERVER_DATASTORE,
)

RELATIONSHIP_VM_TO_NIC = \
    'cloudify.relationships.vsphere.server_connected_to_nic'


def get_connected_networks(node_instance, nics_from_props):
    """ Create a list of dictionaries that merges nics specified
    in the VM node properties and those created via relationships.
    :param _ctx: The VMs current context.
    :param nics_from_props: A list of networks
        defined under connect_networks in _networking.
    :return: A list of networks
        defined under connect_networks in _networking.
    """

    if 'connected_nics' not in \
            node_instance.runtime_properties:
        node_instance.runtime_properties['connected_nics'] = \
            []

    # get all relationship contexts of related nics
    nics_from_rels = find_rels_by_type(
        node_instance, RELATIONSHIP_VM_TO_NIC)

    for rel_nic in nics_from_rels:

        # try to get the connect_network property from the nic.
        try:
            _connect_network = \
                rel_nic.target.instance.runtime_properties[
                    'connected_network']
        except KeyError:
            # If it wasn't provided it's an invalid nic.
            raise NonRecoverableError(
                'No "connect_network" specification for nic {0}.'.format(
                    rel_nic.target.instance.id))

        if not _connect_network.get('name'):
            _connect_network['name'] = \
                rel_nic.target.instance.runtime_properties.get('name')

        # If it wasn't provided it's not a valid nic.
        if not _connect_network['name']:
            raise NonRecoverableError(
                'No network name specified for nic {0}.'.format(
                    rel_nic.target.instance.id))

        for prop_nic in nics_from_props:
            # If there is a nic from props that is supposed
            # to use a nic from relationships do so.
            if _connect_network['name'] == prop_nic['name'] and \
                    prop_nic.get('from_relationship'):
                # Merge them.
                prop_nic.update(_connect_network)
                # We can move on to the next nic in the list.
                continue

        # Otherwise go head and add it to the list.
        nics_from_props.append(_connect_network)
        node_instance.runtime_properties[
            'connected_nics'].append(
            rel_nic.target.instance.id)

    return nics_from_props


def validate_connect_network(_network):
    """Judges a connected network.

    :param _network: a defendant.
    :return: a valid connected network dictionary.
    """

    # The charges.
    network_validations = {
        'name': (basestring, None),
        'from_relationship': (bool, False),
        'external': (bool, False),
        'management': (bool, False),
        'switch_distributed': (bool, False),
        'use_dhcp': (bool, True),
        'network': (basestring, None),
        'gateway': (basestring, None),
        'ip': (basestring, None)
    }

    # Assumed innocent until proven guilty.
    validation_error = False
    # As proper bureaucrats, we always prepare lists.
    validation_error_messages = ['Network failed validation: ']

    if not _network.get('name'):
        # John/Jane Doe.
        validation_error = True
        validation_error_messages.append(
            'All networks connected to a server must have a name specified.')
        del network_validations['name']

    # We review each charge as a distinct offense.
    for key, value in _network.items():

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
        raise NonRecoverableError(str(validation_error_messages))

    # We return the citizen its rights.
    for validation_key, (_, default_value) in network_validations.items():
        _network[validation_key] = default_value

    return _network


def create_new_server(
        ctx,
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
        custom_attributes,
        # Backwards compatibility- only linux was really working
        os_family='linux',
        cdrom_image=None,
        vm_folder=None,
        extra_config=None,
        ):
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info(
        'Creating new server with name: {name}'.format(name=vm_name))

    # This should be debug, but left as info until CFY-4867 makes logs more
    # visible
    ctx.logger.info(
        'Server properties: {properties}'.format(
            properties=prepare_for_log(server),
        )
    )

    ctx.logger.info(
        'Cdrom path: {cdrom}'.format(
            cdrom=cdrom_image,
        )
    )

    if isinstance(allowed_hosts, basestring):
        allowed_hosts = [allowed_hosts]
    if isinstance(allowed_clusters, basestring):
        allowed_clusters = [allowed_clusters]
    if isinstance(allowed_datastores, basestring):
        allowed_datastores = [allowed_datastores]

    domain = networking.get('domain')
    dns_servers = networking.get('dns_servers')
    connect_networks = get_connected_networks(
        ctx.instance,
        networking.get('connect_networks', []))

    # This should be debug, but left as info until CFY-4867 makes logs more
    # visible
    ctx.logger.info(
        'Network properties: {properties} {connect_networks}'.format(
            properties=prepare_for_log(networking),
            connect_networks=connect_networks
        )
    )

    if connect_networks:
        err_msg = "No more than one %s network can be specified."
        if len([network for network in connect_networks
                if network.get('external', False)]) > 1:
            raise NonRecoverableError(err_msg % 'external')
        if len([network for network in connect_networks
                if network.get('management', False)]) > 1:
            raise NonRecoverableError(err_msg % 'management')

        for network_index in range(0, len(connect_networks)):
            network = connect_networks.pop(network_index)
            ctx.logger.info('connected_network: {0}'.format(network))
            validate_connect_network(network)
            if network['external']:
                connect_networks.insert(0, network)
            else:
                connect_networks.append(network)
        del network_index

    connection_config = server_client.cfg
    datacenter_name = connection_config['datacenter_name']
    resource_pool_name = connection_config['resource_pool_name']
    # auto_placement deprecated- deprecation warning emitted where it is
    # actually used.
    auto_placement = connection_config.get('auto_placement', True)
    template_name = server['template']
    cpus = server['cpus']
    memory = server['memory']

    # Computer name may only contain A-Z, 0-9, and hyphens
    # May not be entirely digits
    valid_name = True
    if vm_name.strip(string.digits) == '':
        valid_name = False
    elif vm_name.strip(string.letters + string.digits + '-') != '':
        valid_name = False
    if not valid_name:
        raise NonRecoverableError(
            'Computer name must contain only A-Z, a-z, 0-9, '
            'and hyphens ("-"), and must not consist entirely of '
            'numbers. Underscores will be converted to hyphens. '
            '"{name}" was not valid.'.format(name=vm_name)
        )

    ctx.logger.info('Creating server called {name}'.format(name=vm_name))
    server_obj = server_client.create_server(
        auto_placement,
        cpus,
        datacenter_name,
        memory,
        connect_networks,
        resource_pool_name,
        template_name,
        vm_name,
        windows_password,
        windows_organization,
        windows_timezone,
        agent_config,
        custom_sysprep,
        custom_attributes,
        os_family,
        domain,
        dns_servers,
        allowed_hosts,
        allowed_clusters,
        allowed_datastores,
        cdrom_image=cdrom_image,
        vm_folder=vm_folder,
        extra_config=extra_config)
    ctx.logger.info('Successfully created server called {name}'.format(
                    name=vm_name))
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj._moId
    ctx.instance.runtime_properties['name'] = vm_name
    _update_vm_properties(ctx, server_obj)


@op
@with_server_client
def start(
        ctx,
        server_client,
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
        cdrom_image=None,
        vm_folder=None,
        extra_config=None,
        ):
    ctx.logger.debug("Checking whether server exists...")

    server_obj = None
    if use_external_resource and "name" in server:
        server_obj = server_client.get_server_by_name(server.get('name'))
        if server_obj is None:
            raise NonRecoverableError(
                'A VM with name {0} was not found.'.format(
                    server.get('name')))
        ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj.id
        ctx.instance.runtime_properties['name'] = server_obj.name
        ctx.instance.runtime_properties[NETWORKS] = \
            server_client.get_vm_networks(server_obj)
        ctx.instance.runtime_properties['use_external_resource'] = True
    else:
        for key in ["cpus", "memory", "template"]:
            if not server.get(key):
                raise NonRecoverableError('{0} is not provided.'.format(key))
    if server_obj is None:
        server_obj = get_server_by_context(ctx, server_client,
                                           server, os_family)
    if server_obj is None:
        ctx.logger.info("Server does not exist, creating from scratch.")
        create_new_server(
            ctx,
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
            custom_attributes,
            os_family=os_family,
            cdrom_image=cdrom_image,
            vm_folder=vm_folder,
            extra_config=extra_config
            )
    else:
        server_client.update_server(server=server_obj,
                                    cdrom_image=cdrom_image,
                                    extra_config=extra_config)
        if enable_start_vm:
            ctx.logger.info("Server already exists, powering on.")
            server_client.start_server(server=server_obj)
            ctx.logger.info("Server powered on.")
        else:
            ctx.logger.info("Server already exists, but will not be powered"
                            "on as enable_start_vm is set to false")
        _get_existing_server_details(ctx, server_client, server_obj)
        _update_vm_properties(ctx, server_obj)


@op
@with_server_client
def shutdown_guest(ctx, server_client, server, os_family):
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to shut down server {name}'.format(
                    name=vm_name))
    server_client.shutdown_server_guest(server_obj)
    ctx.logger.info('Succeessfully shut down server {name}'.format(
                    name=vm_name))


@op
@with_server_client
def stop(ctx, server_client, server, os_family, force_stop=False):
    if (
        ctx.instance.runtime_properties.get('use_external_resource') and
        not force_stop
    ):
        ctx.logger.info('Used existing resource.')
        return
    elif force_stop:
        ctx.logger.info('Stop is forced.')
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        if ctx.instance.runtime_properties.get(VSPHERE_SERVER_ID):
            # skip already deleted host
            raise NonRecoverableError(
                "Cannot stop server - server doesn't exist for node: {0}"
                .format(ctx.instance.id))
        return
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to stop server {name}'.format(name=vm_name))
    server_client.stop_server(server_obj)
    ctx.logger.info('Succeessfully stop server {name}'.format(name=vm_name))


@op
@with_server_client
def freeze_suspend(ctx, server_client, server, os_family):
    if ctx.instance.runtime_properties.get('use_external_resource'):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot suspend server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to suspend server {name}'.format(name=vm_name))
    server_client.suspend_server(server_obj)
    ctx.logger.info('Succeessfully suspended server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def freeze_resume(ctx, server_client, server, os_family):
    if ctx.instance.runtime_properties.get('use_external_resource'):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resume server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to resume server {name}'.format(name=vm_name))
    server_client.start_server(server_obj)
    ctx.logger.info('Succeessfully resumed server {name}'.format(name=vm_name))


@op
@with_server_client
def snapshot_create(ctx, server_client, server, os_family, snapshot_name,
                    snapshot_incremental, snapshot_type):
    if ctx.instance.runtime_properties.get('use_external_resource'):
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

    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot backup server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to backup {snapshot_name} for server {name}'
                    .format(snapshot_name=snapshot_name, name=vm_name))
    server_client.backup_server(server_obj, snapshot_name, snapshot_type)
    ctx.logger.info('Succeessfully backuped server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def snapshot_apply(ctx, server_client, server, os_family, snapshot_name,
                   snapshot_incremental):
    if ctx.instance.runtime_properties.get('use_external_resource'):
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

    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot restore server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to restore {snapshot_name} for server {name}'
                    .format(snapshot_name=snapshot_name, name=vm_name))
    server_client.restore_server(server_obj, snapshot_name)
    ctx.logger.info('Succeessfully restored server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def snapshot_delete(ctx, server_client, server, os_family, snapshot_name,
                    snapshot_incremental):
    if ctx.instance.runtime_properties.get('use_external_resource'):
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

    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot remove backup for server - server doesn't exist for "
            "node: {0}".format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to remove backup {snapshot_name} for server '
                    '{name}'.format(snapshot_name=snapshot_name, name=vm_name))
    server_client.remove_backup(server_obj, snapshot_name)
    ctx.logger.info('Succeessfully removed backup from server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def delete(ctx, server_client, server, os_family, force_delete):
    if (
        ctx.instance.runtime_properties.get('use_external_resource') and
        not force_delete
    ):
        ctx.logger.info('Used existing resource.')
        return
    elif force_delete:
        ctx.logger.info('Delete is forced.')
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        if ctx.instance.runtime_properties.get(VSPHERE_SERVER_ID):
            # skip already deleted host
            raise NonRecoverableError(
                "Cannot delete server - server doesn't exist for node: {0}"
                .format(ctx.instance.id))
        return
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to delete server {name}'.format(name=vm_name))
    server_client.delete_server(server_obj)
    ctx.logger.info('Succeessfully deleted server {name}'.format(
                    name=vm_name))
    remove_runtime_properties(SERVER_RUNTIME_PROPERTIES, ctx)


@op
@with_server_client
def get_state(ctx, server_client, server, networking, os_family, wait_ip):
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot get info - server doesn't exist for node: {0}".format(
                ctx.instance.id,
            )
        )
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Getting state for server {name} ({os_family})'
                    .format(name=vm_name, os_family=os_family))

    if os_family == "other":
        ctx.logger.info("Skip guest checks for other os: {info}"
                        .format(info=repr(server_obj.guest)))
        return True

    nets = ctx.instance.runtime_properties[NETWORKS]
    if server_client.is_server_guest_running(server_obj):
        ctx.logger.info("Server is running, getting network details.")
        ctx.logger.info("Guest info: {info}"
                        .format(info=repr(server_obj.guest)))

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
                        .format(networks=repr(management_networks)))

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
                    net['ip'] = get_ip_from_vsphere_nic_ips(network)

        # if we have some managment network but no ip in such by some reason
        # go and run one more time
        if management_network_name and not manager_network_ip:
            return ctx.operation.retry(
                message="Management IP addresses not yet assigned.",
            )

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
                return ctx.operation.retry(
                    message="Public IP addresses not yet assigned.",
                )
            else:
                ctx.logger.info("Server public IP addresses: {ips}."
                                .format(ips=repr(public_ips)))
        else:
            public_ips = []

        # I am uncertain if the logic here is correct, but as this should be
        # refactored to use the more up to date retry logic it's likely not
        # worth a great deal of attention
        if len(public_ips):
            ctx.logger.debug("Public IP address for {name}: {ip}".format(
                             name=vm_name, ip=public_ips[0]))
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
            public_ip = None
        message += '.'

        ctx.logger.info(
            message.format(
                name=vm_name,
                mgmt=manager_network_ip,
                public=public_ip,
            )
        )
        return True
    ctx.logger.info(
        'Server {server} is not started yet'.format(server=server_obj.name))
    # This should all be handled in the create server logic and use operation
    # retries, but until that is implemented this will have to remain.
    return False


@op
@with_server_client
def resize_server(
        ctx, server_client,
        server, os_family,
        cpus=None, memory=None,
        ):
    if not any((
        cpus,
        memory,
    )):
        ctx.logger.info(
            "Attempt to resize Server with no sizes specified")
        return

    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resize server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))

    server_client.resize_server(
        server_obj,
        cpus=cpus,
        memory=memory,
    )

    for property in 'cpus', 'memory':
        value = locals()[property]
        if value:
            ctx.instance.runtime_properties[property] = value


@op
@with_server_client
def resize(ctx, server_client, server, os_family):
    ctx.logger.warn(
        "This operation may be removed at any point from "
        "cloudify-vsphere-plugin==3. "
        "Please use resize_server (cloudify.interfaces.modify.resize) "
        "instead.",
    )
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot resize server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)

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
        ctx.logger.info('Succeeded resizing server {name}.'.format(
                        name=vm_name))
    else:
        raise NonRecoverableError(
            "Server resize parameters should be specified.")


def _update_vm_properties(ctx, server_obj):
    ctx.instance.runtime_properties[VSPHERE_SERVER_HOST] = str(
        server_obj.summary.runtime.host.name)
    ctx.instance.runtime_properties[VSPHERE_SERVER_DATASTORE] = [
        datastore.name for datastore in server_obj.datastore]


def _get_existing_server_details(ctx, server_client, server_obj):
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj.id
    ctx.instance.runtime_properties['name'] = server_obj.name
    ctx.instance.runtime_properties[VSPHERE_SERVER_DATASTORE_IDS] = [
        datastore.id for datastore in server_obj.datastore]
    ctx.instance.runtime_properties[NETWORKS] = \
        server_client.get_vm_networks(server_obj)
    ctx.instance.runtime_properties['use_existing_resource'] = True
    ctx.instance.runtime_properties['use_external_resource'] = True


def get_vm_name(ctx, server, os_family):
    # VM name may be at most 15 characters for Windows.

    # Expecting an ID in the format <name>_<id>
    name_prefix, id_suffix = ctx.instance.id.rsplit('_', 1)

    if 'name' in server and server['name'] != ctx.instance.id:
        name_prefix = server['name']

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
    return vm_name


def get_server_by_context(ctx, server_client, server, os_family=None):
    ctx.logger.info("Performing look-up for server.")
    if VSPHERE_SERVER_ID in ctx.instance.runtime_properties:
        return server_client.get_server_by_id(
            ctx.instance.runtime_properties[VSPHERE_SERVER_ID])
    elif os_family:
        # Try to get server by name. None will be returned if it is not found
        # This may change in future versions of vmomi
        return server_client.get_server_by_name(
            get_vm_name(ctx, server, os_family))

    raise NonRecoverableError(
        'os_family must be provided if the VM might not exist')
