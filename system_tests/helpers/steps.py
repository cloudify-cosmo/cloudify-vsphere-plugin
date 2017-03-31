from platform_state import (
    get_platform_entities,
    compare_state,
    validate_entity_type,
    supports_prefix_search,
)

from pytest_bdd import given, parsers, when, then
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
    assert entities != {}

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
