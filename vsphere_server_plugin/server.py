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

# Stdlib imports
import string

# Third party imports

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from cloudify_vsphere.utils import op
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
)


def validate_connect_network(network):
    if 'name' not in network.keys():
        raise NonRecoverableError(
            'All networks connected to a server must have a name specified. '
            'Network details: {}'.format(str(network))
        )

    allowed = {
        'name': basestring,
        'from_relationship': bool,
        'management': bool,
        'external': bool,
        'switch_distributed': bool,
        'use_dhcp': bool,
        'network': basestring,
        'gateway': basestring,
        'ip': basestring,
    }

    friendly_type_mapping = {
        basestring: 'string',
        bool: 'boolean',
    }

    for key, value in network.items():
        if key in allowed:
            if not isinstance(value, allowed[key]):
                raise NonRecoverableError(
                    'network.{key} must be of type {expected_type}'.format(
                        key=key,
                        expected_type=friendly_type_mapping[allowed[key]],
                    )
                )
        else:
            raise NonRecoverableError(
                'Key {key} is not valid in a connect_networks network. '
                'Network was {name}. Valid keys are: {valid}'.format(
                    key=key,
                    name=network['name'],
                    valid=','.join(allowed.keys()),
                )
            )

    return True


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

    networks = []
    domain = None
    dns_servers = None

    if isinstance(allowed_hosts, basestring):
        allowed_hosts = [allowed_hosts]
    if isinstance(allowed_clusters, basestring):
        allowed_clusters = [allowed_clusters]
    if isinstance(allowed_datastores, basestring):
        allowed_datastores = [allowed_datastores]

    # This should be debug, but left as info until CFY-4867 makes logs more
    # visible
    ctx.logger.info(
        'Network properties: {properties}'.format(
            properties=prepare_for_log(networking),
        )
    )
    if networking:
        domain = networking.get('domain')
        dns_servers = networking.get('dns_servers')
        connect_networks = networking.get('connect_networks', [])

        err_msg = "No more than one %s network can be specified."
        if len([network for network in connect_networks
                if network.get('external', False)]) > 1:
            raise NonRecoverableError(err_msg % 'external')
        if len([network for network in connect_networks
                if network.get('management', False)]) > 1:
            raise NonRecoverableError(err_msg % 'management')

        for network in connect_networks:
            validate_connect_network(network)
            net = {
                'name': network['name'],
                'from_relationship': network.get('from_relationship', False),
                'external': network.get('external', False),
                'switch_distributed': network.get('switch_distributed',
                                                  False),
                'use_dhcp': network.get('use_dhcp', True),
                'network': network.get('network'),
                'gateway': network.get('gateway'),
                'ip': network.get('ip'),
            }
            if net['external']:
                networks.insert(
                    0,
                    net,
                )
            else:
                networks.append(
                    net,
                )

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
        os_family,
        domain,
        dns_servers,
        allowed_hosts,
        allowed_clusters,
        allowed_datastores)
    ctx.logger.info('Successfully created server called {name}'.format(
                    name=vm_name))
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj._moId
    ctx.instance.runtime_properties['name'] = vm_name


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
        use_existing_resource,
        ):
    ctx.logger.debug("Checking whether server exists...")

    server_obj = None
    if use_existing_resource and "name" in server:
        server_obj = server_client.get_server_by_name(server.get("name"))
        if server_obj is None:
            raise NonRecoverableError('Have not found preexisting vm')
        ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server_obj.id
        ctx.instance.runtime_properties['name'] = server_obj.name
        ctx.instance.runtime_properties[NETWORKS] = \
            server_client.get_vm_networks(server_obj)
        ctx.instance.runtime_properties['use_existing_resource'] = True
    else:
        for key in ["cpus", "memory", "template"]:
            if not server.get(key):
                raise NonRecoverableError('{} is not provided.'.format(key))
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
            )
    else:
        ctx.logger.info("Server already exists, powering on.")
        server_client.start_server(server_obj)
        ctx.logger.info("Server powered on.")


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
def stop(ctx, server_client, server, os_family):
    if ctx.instance.runtime_properties.get('use_existing_resource'):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot stop server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to stop server {name}'.format(name=vm_name))
    server_client.stop_server(server_obj)
    ctx.logger.info('Succeessfully stop server {name}'.format(name=vm_name))


@op
@with_server_client
def freeze_suspend(ctx, server_client, server, os_family):
    if ctx.instance.runtime_properties.get('use_existing_resource'):
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
    if ctx.instance.runtime_properties.get('use_existing_resource'):
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
                    snapshot_incremental):
    if ctx.instance.runtime_properties.get('use_existing_resource'):
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
    server_client.backup_server(server_obj, snapshot_name)
    ctx.logger.info('Succeessfully backuped server {name}'
                    .format(name=vm_name))


@op
@with_server_client
def snapshot_apply(ctx, server_client, server, os_family, snapshot_name,
                   snapshot_incremental):
    if ctx.instance.runtime_properties.get('use_existing_resource'):
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
    if ctx.instance.runtime_properties.get('use_existing_resource'):
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
def delete(ctx, server_client, server, os_family):
    if ctx.instance.runtime_properties.get('use_existing_resource'):
        ctx.logger.info('Used existing resource.')
        return
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot delete server - server doesn't exist for node: {0}"
            .format(ctx.instance.id))
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Preparing to delete server {name}'.format(name=vm_name))
    server_client.delete_server(server_obj)
    ctx.logger.info('Succeessfully deleted server {name}'.format(
                    name=vm_name))
    remove_runtime_properties(SERVER_RUNTIME_PROPERTIES, ctx)


@op
@with_server_client
def get_state(ctx, server_client, server, networking, os_family):
    server_obj = get_server_by_context(ctx, server_client, server, os_family)
    if server_obj is None:
        raise NonRecoverableError(
            "Cannot get info - server doesn't exist for node: {0}".format(
                ctx.instance.id,
            )
        )
    vm_name = get_vm_name(ctx, server, os_family)
    ctx.logger.info('Getting state for server {name}'.format(name=vm_name))

    nets = ctx.instance.runtime_properties[NETWORKS]
    if server_client.is_server_guest_running(server_obj):
        ctx.logger.debug("Server is running, getting network details.")
        networks = networking.get('connect_networks', []) if networking else []
        manager_network_ip = None
        management_networks = \
            [network['name'] for network
             in networking.get('connect_networks', [])
             if network.get('management', False)]
        management_network_name = (management_networks[0]
                                   if len(management_networks) == 1
                                   else None)

        # We must obtain IPs at this stage, as they are not populated until
        # after the VM is fully booted
        for network in server_obj.guest.net:
            network_name = network.network
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
                        'Retrying.'.format(server=server_obj)
                    )
                    # This should all be handled in the create server logic
                    # and use operation retries, but until that is implemented
                    # this will have to remain.
                    return False
            for net in nets:
                if net['name'] == network_name:
                    net['ip'] = get_ip_from_vsphere_nic_ips(network)

        ctx.instance.runtime_properties[NETWORKS] = nets
        try:
            ctx.instance.runtime_properties[IP] = (
                manager_network_ip or
                get_ip_from_vsphere_nic_ips(server_obj.guest.net[0])
            )
        except IndexError:
            ctx.logger.warn("Server has no IP addresses.")
            ctx.instance.runtime_properties[IP] = None

        if len(server_obj.guest.net) > 0:
            public_ips = [
                server_client.get_server_ip(server_obj, network['name'])
                for network in networks
                if network.get('external', False)]

            if public_ips is None or None in public_ips:
                return ctx.operation.retry(
                    message="IP addresses not yet assigned.",
                )

            # This should be debug, but left as info until CFY-4867 makes logs
            # more visible
            ctx.logger.info("Server public IP addresses: %s."
                            % ", ".join(public_ips))
        else:
            public_ips = []

        # I am uncertain if the logic here is correct, but as this should be
        # refactored to use the more up to date retry logic it's likely not
        # worth a great deal of attention
        if len(public_ips) == 1:
            ctx.logger.debug('Checking public IP for {name}'.format(
                             name=vm_name))
            public_ip = public_ips[0]
            ctx.logger.debug("Public IP address for {name}: {ip}".format(
                             name=vm_name, ip=public_ip))
            if public_ip is None:
                ctx.logger.info('Public IP not yet set for {server}'
                                .format(server=server_obj))
                # This should all be handled in the create server logic
                # and use operation retries, but until that is implemented
                # this will have to remain.
                return False
            ctx.instance.runtime_properties[PUBLIC_IP] = public_ips[0]
        else:
            ctx.logger.debug('Public IP check not required for {server}'
                             .format(server=server_obj))
            # Ensure the property still exists
            ctx.instance.runtime_properties[PUBLIC_IP] = None

        message = 'Server {name} has started'
        if manager_network_ip:
            message += ' with management IP {mgmt}'
        if len(public_ips) > 0:
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
        'Server {server} is not started yet'.format(server=server_obj))
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
