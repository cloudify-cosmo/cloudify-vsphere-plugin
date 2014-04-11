__author__ = 'Oleksandr_Raskosov'


from cloudify.decorators import operation
from vsphere_plugin_common import with_network_client


@operation
@with_network_client
def create(ctx, network_client, **kwargs):
    network = {
        'name': ctx.node_id,
    }
    network.update(ctx.properties['network'])

    port_group_name = network['name']
    vlan_id = network['vlan_id']
    vswitch_name = network['vswitch_name']
    network_client.create_port_group(port_group_name, vlan_id, vswitch_name)


@operation
@with_network_client
def delete(ctx, network_client, **kwargs):
    port_group_name = ctx.node_id
    network_client.delete_port_group(port_group_name)
