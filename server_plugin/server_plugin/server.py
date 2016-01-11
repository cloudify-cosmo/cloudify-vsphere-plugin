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
                                   remove_runtime_properties)


VSPHERE_SERVER_ID = 'vsphere_server_id'
PUBLIC_IP = 'public_ip'
NETWORKS = 'networks'
IP = 'ip'
SERVER_RUNTIME_PROPERTIES = [VSPHERE_SERVER_ID, PUBLIC_IP, NETWORKS, IP]


def create_new_server(server_client):
    server = {
        'name': ctx.instance.id,
    }
    server.update(ctx.node.properties['server'])
    vm_name = get_vm_name(server)
    ctx.logger.info('Creating new server with name: {name}'
                    .format(name=vm_name))

    ctx.logger.info("Server node info: \n%s." %
                    "".join("%s: %s" % item
                            for item in server.items()))
    networks = []
    domain = None
    dns_servers = None
    networking = ctx.node.properties.get('networking')

    ctx.logger.info("Networking node info: \n%s." %
                    "".join("%s: %s" % item
                            for item in networking.items()))
    if networking:
        domain = networking.get('domain')
        dns_servers = networking.get('dns_servers')
        connect_networks = networking.get('connect_networks', [])

        err_msg = "No more that one %s network can be specified."
        if len([network for network in connect_networks
                if network.get('external', False)]) > 1:
            ctx.logger.error(err_msg % 'external')
            raise cfy_exc.NonRecoverableError(err_msg % 'external')
        if len([network for network in connect_networks
                if network.get('management', False)]) > 1:
            ctx.logger.error(err_msg % 'management')
            raise cfy_exc.NonRecoverableError(err_msg % 'management')

        for network in connect_networks:
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

    if os_type.lower() == 'windows':
        # Computer name for windows may contain A-Z, 0-9, and hyphens
        # May not be entirely digits
        valid_name = True
        if vm_name.strip(string.digits) == '':
            valid_name = False
        elif vm_name.strip(string.letters + string.digits + '-') != '':
            valid_name = False
        if not valid_name:
            raise cfy_exc.NonRecoverableError(
                'Computer name for Windows must contain only A-Z, a-z, 0-9, '
                'and hyphens ("-"), and must not consist entirely of '
                'numbers. "{name}" was not valid.'.format(name=vm_name)
            )

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
    ctx.logger.info('Created server {name} with ID {id}'
                    .format(name=vm_name, id=server._moId))
    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server._moId


@operation
@with_server_client
def start(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        ctx.logger.info("Creating server from scratch.")
        create_new_server(server_client)
    else:
        server_client.start_server(server)


@operation
@with_server_client
def shutdown_guest(server_client, **kwargs):
    server = get_server_by_context(server_client)
    vm_name = get_vm_name(ctx.node.properties['server'])
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(vm_name))
    server_client.shutdown_server_guest(server)


@operation
@with_server_client
def stop(server_client, **kwargs):
    server = get_server_by_context(server_client)
    vm_name = get_vm_name(ctx.node.properties['server'])
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot stop server - server doesn't exist for node: {0}"
            .format(vm_name))
    server_client.stop_server(server)


@operation
@with_server_client
def delete(server_client, **kwargs):
    server = get_server_by_context(server_client)
    vm_name = get_vm_name(ctx.node.properties['server'])
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot delete server - server doesn't exist for node: {0}"
            .format(vm_name))
    server_client.delete_server(server)
    remove_runtime_properties(SERVER_RUNTIME_PROPERTIES, ctx)


@operation
@with_server_client
def get_state(server_client, **kwargs):
    ctx.logger.debug("Entering server state validation procedure.")
    server = get_server_by_context(server_client)
    ctx.logger.info('Getting state for server {server}'.format(server=server))
    if server_client.is_server_guest_running(server):
        ctx.logger.info("Server is running.")
        networking = ctx.node.properties.get('networking')
        networks = networking.get('connect_networks', []) if networking else []
        ips = {}
        manager_network_ip = None
        management_networks = \
            [network['name'] for network
             in ctx.node.properties['networking'].get('connect_networks', [])
             if network.get('management', False)]
        management_network_name = (management_networks[0]
                                   if len(management_networks) == 1
                                   else None)

        for network in server.guest.net:
            network_name = network.network
            if management_network_name and \
                    (network_name == management_network_name):
                manager_network_ip = (network.ipAddress[0]
                                      if len(network.ipAddress) > 0
                                      else None)
                ctx.logger.info("Server management ip address: {0}"
                                .format(manager_network_ip))
                if manager_network_ip is None:
                    ctx.logger.info('Manager network IP not yet present for '
                                    '{server}.'.format(server=server))
                    return False
            ips[network_name] = network.ipAddress[0]

        ctx.instance.runtime_properties['networks'] = ips
        ctx.instance.runtime_properties['ip'] = \
            (manager_network_ip
             or (server.guest.net[0].ipAddress[0]
                 if len(server.guest.net) > 0
                 else None)
             )

        public_ips = [server_client.get_server_ip(server, network['name'])
                      for network in networks
                      if network.get('external', False)]
        if public_ips is None or None in public_ips:
            return ctx.operation.retry(
                message="IP addresses not yet assigned.",
            )
        for public_ip in public_ips:
            if public_ip.startswith('169.254.'):
                return ctx.operation.retry(
                    message="DHCP IP not yet assigned.",
                )

        # TODO: Decide what to do if we have None in ips. This means that a
        # network we care about has no IP address assigned
        ctx.logger.info("Server public IP addresses: %s."
                        % ", ".join(public_ips))

        if len(public_ips) == 1:
            ctx.logger.info('Checking public IP for {server}'
                            .format(server=server))
            public_ip = public_ips[0]
            ctx.logger.info("Public IP address for {server}: {ip}"
                            .format(server=server, ip=public_ip))
            if public_ip is None:
                ctx.logger.info('Public IP not yet set for {server}'
                                .format(server=server))
                return False
            ctx.instance.runtime_properties[PUBLIC_IP] = public_ips[0]
        else:
            ctx.logger.info('Public IP check not required for {server}'
                            .format(server=server))

        ctx.logger.info("Server is available through next IP addresses:\n"
                        "Management: %s\n"
                        "Public: %s.\n" % (manager_network_ip, public_ips[0]))

        return True
    ctx.logger.info('Server {server} is not started yet'.format(server=server))
    return False


@operation
@with_server_client
def resize(server_client, **kwargs):
    server = get_server_by_context(server_client)
    ctx.logger.info("Resizing server {server}".format(server=server))
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot resize server - server doesn't exist for node: {0}"
            .format(ctx.node.id))

    update = {
        'cpus': ctx.instance.runtime_properties.get('cpus'),
        'memory': ctx.instance.runtime_properties.get('memory')
        }

    if any(update.values()):
        ctx.logger.info("Server new parameters: cpus - {0}, memory - {1}"
                        .format(update['cpus'] or 'no changes',
                                update['memory'] or 'no changes')
                        )
        server_client.resize_server(server, **update)
    else:
        raise cfy_exc.NonRecoverableError(
            "Server resize parameters should be specified.")


def get_vm_name(server):
    # VM name may be at most 15 characters for Windows.
    os_type = ctx.node.properties.get('os_family', 'linux')

    # Expecting an ID in the format <name>_<id>
    name_prefix, id_suffix = ctx.instance.id.rsplit('_', 1)

    if 'name' in server:
        name_prefix = server['name']

    if os_type.lower() == 'windows':
        max_prefix = 14 - (len(id_suffix) + 1)
        name_prefix = name_prefix[:max_prefix]

    vm_name = '-'.join([name_prefix, id_suffix])
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
