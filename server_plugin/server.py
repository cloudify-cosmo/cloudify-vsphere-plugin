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

import cloudify
import vsphere_plugin_common as vpc

from cloudify import decorators
from cloudify import exceptions as cfy_exc

ctx = cloudify.ctx
operation = decorators.operation
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
    vpc.transform_resource_name(server, ctx)

    vm_name = server['name']
    networks = []
    domain = None
    dns_servers = None
    networking = ctx.node.properties.get('networking')

    if networking:
        domain = networking.get('domain')
        dns_servers = networking.get('dns_servers')
        connect_networks = networking.get('connect_networks', [])

        if len([network for network in connect_networks
                if network.get('external', False)]) > 1:
            raise cfy_exc.NonRecoverableError(
                "No more that one external network can be specified")
        if len([network for network in connect_networks
                if network.get('management', False)]) > 1:
            raise cfy_exc.NonRecoverableError(
                "No more that one management network can be specified")

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

    connection_config = vpc.ConnectionConfig().get()
    connection_config.update(ctx.node.properties.get('connection_config'))
    datacenter_name = connection_config['datacenter_name']
    resource_pool_name = connection_config['resource_pool_name']
    auto_placement = connection_config['auto_placement']
    template_name = server['template']
    cpus = server['cpus']
    memory = server['memory']

    server = server_client.create_server(auto_placement,
                                         cpus,
                                         datacenter_name,
                                         memory,
                                         networks,
                                         resource_pool_name,
                                         template_name,
                                         vm_name,
                                         domain,
                                         dns_servers)

    ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = server._moId


@operation
@vpc.with_server_client
def start(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        create_new_server(server_client)
    else:
        server_client.start_server(server)


@operation
@vpc.with_server_client
def shutdown_guest(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(ctx.node.id))
    server_client.shutdown_server_guest(server)


@operation
@vpc.with_server_client
def stop(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot stop server - server doesn't exist for node: {0}"
            .format(ctx.node.id))
    server_client.stop_server(server)


@operation
@vpc.with_server_client
def delete(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot delete server - server doesn't exist for node: {0}"
            .format(ctx.node.id))
    server_client.delete_server(server)
    vpc.remove_runtime_properties(SERVER_RUNTIME_PROPERTIES, ctx)


@operation
@vpc.with_server_client
def get_state(server_client, **kwargs):
    server = get_server_by_context(server_client)
    if server_client.is_server_guest_running(server):
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
        if len(public_ips) == 1:
            public_ip = public_ips[0]
            ctx.logger.info("Server public ip address: {0}".format(public_ip))
            if public_ip is None:
                return False
            ctx.instance.runtime_properties[PUBLIC_IP] = public_ips[0]

        return True
    return False


@operation
@vpc.with_server_client
def resize(server_client, **kwargs):
    ctx.logger.info("Resizing server")
    server = get_server_by_context(server_client)
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
            "Server resize parameters should be specified")


def get_server_by_context(server_client):
    if VSPHERE_SERVER_ID in ctx.instance.runtime_properties:
        return server_client.get_server_by_id(
            ctx.instance.runtime_properties[VSPHERE_SERVER_ID])
    return server_client.get_server_by_name(ctx.instance.id)
