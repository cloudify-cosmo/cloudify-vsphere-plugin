#########
# Copyright (c) 2017-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from functools import wraps
from inspect import getargspec

from cloudify import ctx
from cloudify.decorators import operation

try:
    from cloudify.constants import RELATIONSHIP_INSTANCE, NODE_INSTANCE
except ImportError:
    NODE_INSTANCE = 'node-instance'
    RELATIONSHIP_INSTANCE = 'relationship-instance'

from ._compat import unquote


def _get_instance(_ctx):
    if _ctx.type == RELATIONSHIP_INSTANCE:
        return _ctx.source.instance
    else:  # _ctx.type == NODE_INSTANCE
        return _ctx.instance


def _get_node(_ctx):
    if _ctx.type == RELATIONSHIP_INSTANCE:
        return _ctx.source.node
    else:  # _ctx.type == NODE_INSTANCE
        return _ctx.node


def get_args(func):
    """
    recursively collect all args from functions wrapped by decorators.
    """

    args = set()
    if hasattr(func, '__wrapped__'):
        args.update(get_args(func.__wrapped__))
    args.update(getargspec(func).args)
    return args


def op(func):
    """
    This decorator wraps node operations and provides all of the node's
    properties as function inputs.
    Any inputs provided directly to the operation will override corresponding
    properties.

    In order for other decorators to cooperate with @op, they must expose the
    wrapped function object as newfunction.__wrapped__ (this follows the
    convention started by the `decorator` library).
    """

    @operation(resumable=True)
    @wraps(func)
    def wrapper(**kwargs):
        kwargs.setdefault('ctx', ctx)

        requested_inputs = get_args(func)

        processed_kwargs = {}

        # Support both node instance and relationship node instance CTX.
        ctx_node = _get_node(ctx)

        for key in requested_inputs:
            if key in kwargs:
                processed_kwargs[key] = kwargs[key]
                continue
            # TODO: Update this to also support relationship operations.
            processed_kwargs[key] = ctx_node.properties.get(key)

        return func(**processed_kwargs)

    return wrapper


def find_rels_by_type(node_instance, rel_type):
    """Finds all specified relationships of the Cloudify instance.
    :param `cloudify.context.NodeInstanceContext` node_instance:
        Cloudify node instance.
    :param str rel_type: Cloudify relationship type to search
        node_instance.relationships for.
    :returns: List of Cloudify relationships
    """
    return [x for x in node_instance.relationships
            if rel_type in x.type_hierarchy]


def find_instances_by_type_from_rels(node_instance, rel_type, node_type):
    instances = []
    for relationship in find_rels_by_type(node_instance, rel_type):
        if node_type in relationship.target.node.type_hierarchy:
            instances.append(relationship.target.instance)
    return instances


def check_name_for_special_characters(name):

    # See https://kb.vmware.com/kb/2046088
    bad_characters = '%&*$#@!\\/:*?"<>|;\''

    name = unquote(name)

    found = []
    for bad in bad_characters:
        if bad in name:
            found.append(bad)

    if found:
        ctx.logger.warn(
            'Found characters that may cause problems in name. '
            'It is recommended that "{chars}" be avoided. '
            'In a future release such characters will be encoded when '
            'creating new entities on vSphere. '
            'Found: {found}'.format(
                chars=bad_characters,
                found=found,
            )
        )


def logger():
    try:
        logger = ctx.logger
    except RuntimeError as e:
        if 'No context' in str(e):
            logger = logging.getLogger()
        else:
            raise
    return logger


def prepare_for_log(inputs):
    result = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            value = prepare_for_log(value)
        if 'password' in key:
            value = '**********'
        result[key] = value
    return result
