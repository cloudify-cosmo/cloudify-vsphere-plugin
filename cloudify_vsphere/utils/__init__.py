#########
# Copyright (c) 2017-2019 Cloudify Platform Ltd. All rights reserved
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


from functools import wraps
from inspect import getargspec

from cloudify import ctx
from cloudify.decorators import operation


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

        for key in requested_inputs:
            if key in kwargs:
                processed_kwargs[key] = kwargs[key]
                continue
            processed_kwargs[key] = ctx.node.properties.get(key)

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
