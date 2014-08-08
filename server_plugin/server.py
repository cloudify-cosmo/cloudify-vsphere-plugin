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


__author__ = 'Oleksandr_Raskosov'


from cloudify.decorators import operation
from vsphere_plugin_common import (with_server_client,
                                   NetworkClient)


VSPHERE_SERVER_ID = 'vsphere_server_id'


def create_new_server(ctx, server_client):
    server = {
        'name': ctx.node_id,
    }
    server.update(ctx.properties['server'])

    vm_name = server['name']
    networks = []
    management_set = False
    use_dhcp = True
    domain = None
    dns_servers = None

    if ('networking' in ctx.properties) and\
            ctx.properties['networking']:
        networking_properties = ctx.properties.get('networking')
        use_dhcp = networking_properties['use_dhcp']
        if 'domain' in networking_properties:
            domain = networking_properties['domain']
        if 'dns_servers' in networking_properties:
            dns_servers = networking_properties['dns_servers']
        if ('management_network' in networking_properties)\
                and networking_properties['management_network']:
            networks.append(networking_properties['management_network'])
            management_set = True
        if 'connected_networks' in networking_properties:
            cntd_networks = networking_properties['connected_networks']
            for x in cntd_networks.split(','):
                networks.append({'name': x.strip()})

    network_nodes_runtime_properties = ctx.capabilities.get_all().values()
    if network_nodes_runtime_properties and not management_set:
        # Known limitation
        raise RuntimeError("vSphere server with multi-NIC requires "
                           "'management_network' which was not supplied")
    network_client = NetworkClient().get(
        config=ctx.properties.get('connection_config'))
    nics = None
    if use_dhcp:
        nics = [
            {'name': n['node_id']}
            for n in network_nodes_runtime_properties
            if network_client.get_port_group_by_name(n['node_id'])
        ]
    else:
        nics = [
            {
                'name': n['node_id'],
                'network': n['network'],
                'gateway': n['gateway'],
                'ip': n['ip']
            }
            for n in network_nodes_runtime_properties
            if network_client.get_port_group_by_name(n['node_id'])
        ]

    if nics:
        networks.extend(nics)

    connection_config = ctx.properties.get('connection_config')
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
                                         use_dhcp,
                                         domain,
                                         dns_servers)

    ctx[VSPHERE_SERVER_ID] = server._moId


@operation
@with_server_client
def start(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is not None:
        server_client.start_server(server)

    create_new_server(ctx, server_client)


@operation
@with_server_client
def shutdown_guest(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is None:
        raise RuntimeError(
            "Cannot shutdown server guest - server doesn't exist for node: {0}"
            .format(ctx.node_id))
    server_client.shutdown_server_guest(server)


@operation
@with_server_client
def stop(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is None:
        raise RuntimeError(
            "Cannot stop server - server doesn't exist for node: {0}"
            .format(ctx.node_id))
    server_client.stop_server(server)


@operation
@with_server_client
def delete(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is None:
        raise RuntimeError(
            "Cannot delete server - server doesn't exist for node: {0}"
            .format(ctx.node_id))
    server_client.delete_server(server)


@operation
@with_server_client
def get_state(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server_client.is_server_guest_running(server):
        ips = {}
        manager_network_ip = None
        management_network_name =\
            ctx.properties['networking']['management_network']['name'].lower()
        for network in server.guest.net:
            network_name = network.network.lower()
            if management_network_name and\
                    (network_name == management_network_name):
                manager_network_ip = network.ipAddress[0]
            ips[network.network] = network.ipAddress[0]
        ctx['networks'] = ips
        ctx['ip'] = manager_network_ip
        return True
    return False


def get_server_by_context(server_client, ctx):
    if VSPHERE_SERVER_ID in ctx:
        return server_client.get_server_by_id(ctx[VSPHERE_SERVER_ID])
    return server_client.get_server_by_name(ctx.node_id)
