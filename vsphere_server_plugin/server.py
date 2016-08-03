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

import string

from cloudify import ctx
from cloudify.decorators import operation
from cloudify import exceptions as cfy_exc
from vsphere_plugin_common import (with_server_client,
                                   ConnectionConfig,
                                   remove_runtime_properties,
                                   prepare_for_log,
                                   get_ip_from_vsphere_nic_ips)
from vsphere_plugin_common.constants import (
    VSPHERE_SERVER_ID,
    PUBLIC_IP,
    NETWORKS,
    IP,
    SERVER_RUNTIME_PROPERTIES,
)


def validate_connect_network(network):
    if 'name' not in network.keys():
        raise cfy_exc.NonRecoverableError(
            'All networks connected to a server must have a name specified. '
            'Network details: {}'.format(str(network))
        )

    allowed = {
        'name': basestring,
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
                raise cfy_exc.NonRecoverableError(
                    'network.{key} must be of type {expected_type}'.format(
                        key=key,
                        expected_type=friendly_type_mapping[allowed[key]],
                    )
                )
        else:
            raise cfy_exc.NonRecoverableError(
                'Key {key} is not valid in a connect_networks network. '
                'Network was {name}. Valid keys are: {valid}'.format(
                    key=key,
                    name=network['name'],
                    valid=','.join(allowed.keys()),
                )
            )

    return True


def create_new_server(server_client):
    server = {}
    server.update(ctx.node.properties['server'])
    vm_name = get_vm_name(server)
    ctx.logger.info('Creating new server with name: {name}'
                    .format(name=vm_name))

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
    networking = ctx.node.properties.get('networking')

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
            raise cfy_exc.NonRecoverableError(err_msg % 'external')
        if len([network for network in connect_networks
                if network.get('management', False)]) > 1:
            raise cfy_exc.NonRecoverableError(err_msg % 'management')

        for network in connect_networks:
            validate_connect_network(network)
            if network.get('external', False):
                networks.insert(
                    0,
                    {'name': network['name'],
                     'external': True,
                     'switch_distributed': network.get('switch_distributed',
                                                       False),
                     'use_dhcp': network.get('use_dhcp', True),
                     'network': network.get('network'),
                     'gateway': network.get('gateway'),
                     'ip': network.get('ip'),
                     })
            else:
                networks.append(
                    {'name': network['name'],
                     'external': False,
                     'switch_distributed': network.get('switch_distributed',
                                                       False),
                     'use_dhcp': network.get('use_dhcp', True),
                     'network': network.get('network'),
                     'gateway': network.get('gateway'),
                     'ip': network.get('ip'),
                     })

    connection_config = ConnectionConfig().get()
    connection_config.update(ctx.node.properties.get('connection_config'))
    datacenter_name = connection_config['datacenter_name']
    resource_pool_name = connection_config['resource_pool_name']
    auto_placement = connection_config['auto_placement']
    template_name = server['template']
    cpus = server['cpus']
    memory = server['memory']
    # Backwards compatibility- only linux was really working
    os_type = ctx.node.properties.get('os_family', 'linux')

    # Computer name may only contain A-Z, 0-9, and hyphens
    # May not be entirely digits
    valid_name = True
    if vm_name.strip(string.digits) == '':
        valid_name = False
    elif vm_name.strip(string.letters + string.digits + '-') != '':
        valid_name = False
    if not valid_name:
        raise cfy_exc.NonRecoverableError(
            'Computer name must contain only A-Z, a-z, 0-9, '
            'and hyphens ("-"), and must not consist entirely of '
            'numbers. Underscores will be converted to hyphens. '
            '"{name}" was not valid.'.format(name=vm_name)
        )

    ctx.logger.info('Creating server called {name}'.format(name=vm_name))
    server = server_client.create_server(auto_placement,
                                         cpus,
                                         datacenter_name,
                                         memory,
                                         networks,
                                         resource_pool_name,
                                         template_name,
                                         vm_name,
                                         os_type,
                                         domain,
                                         dns_servers)
    ctx.logger.info('Successfully created server called {name}'.format(
                    name=vm_name))
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server._moId
    ctx.instance.runtime_properties['name'] = vm_name


@operation
@with_server_client
def start(server_client, **kwargs):
    ctx.logger.debug("Checking whether server exists...")
    server = get_server_by_context(server_client)
    if server is None:
        ctx.logger.info("Server does not exist, creating from scratch.")
        create_new_server(server_client)
    else:
        ctx.logger.info("Server already exists, powering on.")
        server_client.start_server(server)
        ctx.logger.info("Server powered on.")


@operation
@with_server_client
def shutdown_guest(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(server))
    vm_name = get_vm_name(ctx.node.properties['server'])
    ctx.logger.info('Preparing to shut down server {name}'.format(
                    name=vm_name))
    server_client.shutdown_server_guest(server)
    ctx.logger.info('Succeessfully shut down server {name}'.format(
                    name=vm_name))


@operation
@with_server_client
def stop(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot stop server - server doesn't exist for node: {0}"
            .format(server))
    vm_name = get_vm_name(ctx.node.properties['server'])
    ctx.logger.info('Preparing to stop server {name}'.format(name=vm_name))
    server_client.stop_server(server)
    ctx.logger.info('Succeessfully stop server {name}'.format(name=vm_name))


@operation
@with_server_client
def delete(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot delete server - server doesn't exist for node: {0}"
            .format(server))
    vm_name = get_vm_name(ctx.node.properties['server'])
    ctx.logger.info('Preparing to delete server {name}'.format(name=vm_name))
    server_client.delete_server(server)
    ctx.logger.info('Succeessfully deleted server {name}'.format(
                    name=vm_name))
    remove_runtime_properties(SERVER_RUNTIME_PROPERTIES, ctx)


@operation
@with_server_client
def get_state(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot get info - server doesn't exist for node: {0}".format(
                server,
            )
        )
    vm_name = get_vm_name(ctx.node.properties['server'])
    ctx.logger.info('Getting state for server {name}'.format(name=vm_name))

    nets = ctx.instance.runtime_properties[NETWORKS]
    if server_client.is_server_guest_running(server):
        ctx.logger.debug("Server is running, getting network details.")
        networking = ctx.node.properties.get('networking')
        networks = networking.get('connect_networks', []) if networking else []
        manager_network_ip = None
        management_networks = \
            [network['name'] for network
             in ctx.node.properties['networking'].get('connect_networks', [])
             if network.get('management', False)]
        management_network_name = (management_networks[0]
                                   if len(management_networks) == 1
                                   else None)

        # We must obtain IPs at this stage, as they are not populated until
        # after the VM is fully booted
        for network in server.guest.net:
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
                        'Retrying.'.format(server=server)
                    )
                    # This should all be handled in the create server logic
                    # and use operation retries, but until that is implemented
                    # this will have to remain.
                    return False
            for net in nets:
                if net['name'] == network_name:
                    net['ip'] = get_ip_from_vsphere_nic_ips(network)

        ctx.instance.runtime_properties[NETWORKS] = nets
        ctx.instance.runtime_properties[IP] = \
            (manager_network_ip or
             get_ip_from_vsphere_nic_ips(server.guest.net[0]))

        public_ips = [server_client.get_server_ip(server, network['name'])
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
                                .format(server=server))
                # This should all be handled in the create server logic
                # and use operation retries, but until that is implemented
                # this will have to remain.
                return False
            ctx.instance.runtime_properties[PUBLIC_IP] = public_ips[0]
        else:
            ctx.logger.debug('Public IP check not required for {server}'
                             .format(server=server))
            # Ensure the property still exists
            ctx.instance.runtime_properties[PUBLIC_IP] = None

        message = 'Server {name} has started with management IP {mgmt}'
        if len(public_ips) > 0:
            public_ip = public_ips[0]
            message += ' and public IP {public}'
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
    ctx.logger.info('Server {server} is not started yet'.format(server=server))
    # This should all be handled in the create server logic and use operation
    # retries, but until that is implemented this will have to remain.
    return False


@operation
@with_server_client
def resize(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot resize server - server doesn't exist for node: {0}"
            .format(ctx.node.id))
    vm_name = get_vm_name(ctx.node.properties['server'])

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
        server_client.resize_server(server, **update)
        ctx.logger.info('Succeeded resizing server {name}.'.format(
                        name=vm_name))
    else:
        raise cfy_exc.NonRecoverableError(
            "Server resize parameters should be specified.")


def get_vm_name(server):
    # VM name may be at most 15 characters for Windows.
    os_type = ctx.node.properties.get('os_family', 'linux')

    # Expecting an ID in the format <name>_<id>
    name_prefix, id_suffix = ctx.instance.id.rsplit('_', 1)

    if 'name' in server and server['name'] != ctx.instance.id:
        name_prefix = server['name']

    if os_type.lower() == 'windows':
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


def get_server_by_context(server_client):
    ctx.logger.info("Performing look-up for server.")
    if VSPHERE_SERVER_ID in ctx.instance.runtime_properties:
        return server_client.get_server_by_id(
            ctx.instance.runtime_properties[VSPHERE_SERVER_ID])
    else:
        # Try to get server by name. None will be returned if it is not found
        # This may change in future versions of vmomi
        server = ctx.node.properties['server']
        return server_client.get_server_by_name(get_vm_name(server))
