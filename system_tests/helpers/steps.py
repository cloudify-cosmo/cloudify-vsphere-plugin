from clients import get_vsphere_client
from platform_state import (
    get_platform_entities,
    compare_state,
    validate_entity_type,
    supports_prefix_search,
)

from pytest_bdd import given, parsers, then, when
import pytest

import time


@given('I know what is on the platform')
def platform_state(tester_conf):
    """
        Caches the state of the platform at the beginning of a test.
    """
    return get_platform_entities(tester_conf)


def pre_check(entity, platform_changes):
    """
        Check whether the platform let us retrieve this entity type.
    """
    assert platform_changes['current'][entity + 's'] != {None: None}, (
        "Could not retrieve entities of type {} from platform.".format(entity)
    )


@then(parsers.cfparse('{num:d} {entity}(s) were created on the platform'))
def new_entity_found(num, entity, platform_changes, tester_conf):
    """
        Check that a specific <num> of entities have been created on the
        platform.
        Valid entities are:
        vm, standard_network, distributed_network
    """
    validate_entity_type(entity)
    pre_check(entity, platform_changes)

    new = get_created_entities(platform_changes)
    entities = new[entity + 's']

    assert len(entities) == num, (
        '{} {} expected to be created. Actual created: {}'.format(num,
                                                                  entity,
                                                                  entities)
    )


@then(parsers.cfparse('{num:d} {entity}(s) were created on the platform '
                      'with resources prefix'))
def new_entity_found_with_prefix(num, entity, platform_changes, tester_conf):
    """
        Check that a specific <num> of entities have been created on the
        platform with a name prefixed with the resources_prefix from the
        config.
        Valid entities are:
        vm, standard_network, distributed_network
    """
    validate_entity_type(entity)
    pre_check(entity, platform_changes)
    supports_prefix_search(entity)

    new = get_created_entities(platform_changes)

    entities = new[entity + 's']

    prefix = tester_conf['resources_prefix']
    prefixed_entities = [
        new_entity for new_entity in entities
        if new_entity.startswith(prefix)
    ]
    assert len(prefixed_entities) == num, (
        '{} {} with prefix {} expected to be created. Actual created: '
        '{}'.format(num,
                    entity,
                    prefix,
                    entities)
    )


@then(parsers.cfparse('{num:d} {entity}(s) were deleted from the platform'))
def old_entities_removed(num, entity, platform_changes, tester_conf):
    """
        Check that a specific <num> of entities have been deleted from the
        platform.
        Valid entities are:
        vm, standard_network, distributed_network
    """
    validate_entity_type(entity)
    pre_check(entity, platform_changes)

    deleted = get_deleted_entities(platform_changes)
    entities = deleted[entity + 's']

    assert len(entities) == num, (
        '{} {} expected to be deleted. Actual deleted: {}'.format(num,
                                                                  entity,
                                                                  entities)
    )


@then(parsers.cfparse('{num:d} {entity}(s) with resources prefix were '
                      'deleted from the platform'))
def old_prefixed_entities_removed(num, entity, platform_changes,
                                  tester_conf):
    """
        Check that a specific <num> of entities have been deleted from the
        platform with a name prefixed with the resources_prefix from the
        config.
        Valid entities are:
        vm, standard_network, distributed_network
    """
    validate_entity_type(entity)
    pre_check(entity, platform_changes)
    supports_prefix_search(entity)

    deleted = get_deleted_entities(platform_changes)
    entities = deleted[entity + 's']

    prefix = tester_conf['resources_prefix']
    prefixed_entities = [
        old_entity for old_entity in entities
        if old_entity.startswith(prefix)
    ]
    assert len(prefixed_entities) == num, (
        '{} {} with prefix {} expected to be deleted. Actual deleted: '
        '{}'.format(num,
                    entity,
                    prefix,
                    entities)
    )


@pytest.fixture(scope='module')
def platform_changes():
    return {}


@then('I know what has been changed on the platform')
def update_platform_state(platform_state, tester_conf, platform_changes):
    """
        Determine what has changed on the platform since the last time the
        platform state was updated by this step or by 'Given I know what is on
        the platform'.
        This must be called before any of the steps that check for created or
        deleted entities.
    """
    # Kludge because packstack environment takes time updating volumes
    time.sleep(2)
    new_state = get_platform_entities(tester_conf)

    changes = compare_state(platform_state, new_state)
    for change_type in changes.keys():
        platform_changes[change_type] = {}
        for entity, change in changes[change_type].items():
            platform_changes[change_type][entity] = change

    for key in platform_state:
        platform_state[key] = new_state[key]


def get_created_entities(platform_changes):
    return platform_changes['created']


def get_deleted_entities(platform_changes):
    return platform_changes['deleted']


@then(parsers.cfparse('local VM {node_name} power state is {state}'))
def check_power_state(node_name, state, environment, tester_conf):
    """
        Assuming only one VM exists in the specified node, check that it
        is in the correct power state- e.g. on or off.
    """
    check_state = get_power_state_name(state)

    vm = get_vm_from_node(node_name, environment, tester_conf)

    assert vm.obj.summary.runtime.powerState == check_state


def get_power_state_name(state):
    state = state.lower()
    power_states = {
        'on': 'poweredOn',
        'off': 'poweredOff',
    }
    check_state = power_states.get(state)
    if not check_state:
        raise ValueError(
            'Only power states the following power states can be checked: '
            '{states}'.format(states=','.join(power_states.keys()))
        )
    return check_state


def get_instances_with_node_id(node_name, environment):
    deployment_instances = environment.cfy.local.instances()['cfy_instances']
    instances = []
    for instance in deployment_instances:
        if instance['node_id'] == node_name:
            instances.append(instance)
    return instances


def get_vm_from_node(node_name, environment, tester_conf):
    vm_name = None
    vms = get_instances_with_node_id(node_name, environment)
    if vms:
        vm_name = vms[0]['runtime_properties']['name']
    assert vm_name is not None, 'Instance {name} not found!'.format(
        name=node_name,
    )

    client = get_vsphere_client(tester_conf)
    vms = client._get_vms()
    vm = None
    for candidate_vm in vms:
        if candidate_vm.name == vm_name:
            vm = candidate_vm
            break
    assert vm is not None, 'VM {name} not found!'.format(name=vm_name)

    return vm


@given(parsers.cfparse(
    'I ensure that local VM {node_name} is powered {state}'
))
def ensure_power_state(node_name, state, environment, tester_conf):
    vm = get_vm_from_node(node_name, environment, tester_conf)
    expected_state = get_power_state_name(state)

    power_func = {
        'on': vm.obj.PowerOn,
        'off': vm.obj.PowerOff,
    }

    power_func.get(state)()

    attempt = 0
    attempts = 30
    delay = 2
    while vm.obj.summary.runtime.powerState != expected_state:
        time.sleep(delay)
        attempt += 1

        assert attempt < attempts, (
            'VM for node did not power {state} within {time} seconds.'.format(
                state=state,
                time=attempts*delay,
            )
        )


@given(parsers.cfparse('I know the last boot time of local VM {node_name}'))
def vm_original_boot_time(node_name, environment, tester_conf):
    vm = get_vm_from_node(node_name, environment, tester_conf)
    return vm.obj.summary.runtime.bootTime


@then(parsers.cfparse(
    'local VM {node_name} has been restarted during this test'
))
def vm_was_rebooted(node_name, environment, vm_original_boot_time, tester_conf):
    vm = get_vm_from_node(node_name, environment, tester_conf)

    assert vm_original_boot_time < vm.obj.summary.runtime.bootTime


@then(parsers.cfparse(
    'local node {node_name} has runtime property {property_name} with value '
    'starting with {prefix}'
))
def runtime_property_of_node_has_prefix(node_name, property_name, prefix,
                                        environment):
    instances = get_instances_with_node_id(node_name, environment)
    for instance in instances:
        assert instance['runtime_properties'][property_name].startswith(
            prefix
        ), (
            'Value "{value}" did not start with prefix "{prefix}"'.format(
                value=instance['runtime_properties'][property_name],
                prefix=prefix,
            )
        )
