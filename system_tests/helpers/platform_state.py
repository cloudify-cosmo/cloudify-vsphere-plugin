from clients import get_vsphere_client


def get_platform_entities(tester_conf):
    client = get_vsphere_client(tester_conf)

    result = {}

    servers = client._get_vms(use_cache=False)
    result['vms'] = {
        server.name: server.id
        for server in servers
    }
    standard_nets = client._get_standard_networks(use_cache=False)
    result['standard_networks'] = {
        standard_net.name: standard_net.id
        for standard_net in standard_nets
    }
    dv_nets = client._get_dv_networks(use_cache=False)
    result['distributed_networks'] = {
        dv_net.name: dv_net.id
        for dv_net in dv_nets
    }
    clusters = client._get_clusters(use_cache=False)
    result['clusters'] = {
        cluster.name: cluster.id
        for cluster in clusters
    }

    return result


def compare_state(old_state, new_state):
    created_entities = {}
    for entity in old_state.keys():
        created_entities[entity] = dict(
            set(new_state[entity].items()) - set(old_state[entity].items())
        )

    deleted_entities = {}
    for entity in old_state.keys():
        deleted_entities[entity] = dict(
            set(old_state[entity].items()) - set(new_state[entity].items())
        )

    return {
        'current': new_state,
        'created': created_entities,
        'deleted': deleted_entities,
    }


def validate_entity_type(entity_type):
    valid_types = [
        'vm',
        'standard_network',
        'distributed_network',
        'cluster',
    ]

    assert entity_type in valid_types, \
        '{} is not a valid type of vsphere entity.'.format(entity_type)


def supports_prefix_search(entity_type):
    supports_prefix = [
        'vm',
        'standard_network',
        'distributed_network',
        'cluster',
    ]

    assert entity_type in supports_prefix, \
        'Entity {} does not support prefix searches.'.format(entity_type)
