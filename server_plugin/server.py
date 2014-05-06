__author__ = 'Oleksandr_Raskosov'


from cloudify.decorators import operation
import vsphere_plugin_common
from vsphere_plugin_common import with_server_client


VSPHERE_SERVER_ID = 'vsphere_server_id'


@operation
@with_server_client
def create(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is not None:
        server.start()
        return

    create_new_server(ctx, server_client)


def create_new_server(ctx, server_client):
    server = {
        'name': ctx.node_id,
    }
    server.update(ctx.properties['server'])

    vm_name = server['name']
    networks = []

    if ('management_network_name' in ctx.properties) and \
            ctx.properties['management_network_name']:
        networks.append({'name': ctx.properties['management_network_name']})

    network_nodes_runtime_properties = ctx.capabilities.get_all().values()
    if network_nodes_runtime_properties and \
            'management_network_name' not in ctx.properties:
        # Known limitation
        raise RuntimeError("vSphere server with multi-NIC requires "
                           "'management_network_name' which was not supplied")
    network_client = vsphere_plugin_common.NetworkClient().get(
        config=ctx.properties.get('connection_config'))
    nics = [
        {'name': n['node_id']}
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
                                         vm_name)

    ctx[VSPHERE_SERVER_ID] = server._moId


@operation
@with_server_client
def start(ctx, server_client, **kwargs):
    server = get_server_by_context(server_client, ctx)
    if server is None:
        raise RuntimeError(
            "Cannot start server - server doesn't exist for node: {0}"
            .format(ctx.node_id))
    server_client.start_server(server)


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
        management_network_name = ctx.properties['management_network_name']
        for network in server.guest.net:
            if management_network_name and network.network.lower() == management_network_name.lower():
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
