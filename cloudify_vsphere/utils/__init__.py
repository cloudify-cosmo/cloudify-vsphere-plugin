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


from copy import deepcopy
from functools import wraps
from inspect import getargspec

from cloudify import ctx
from cloudify.decorators import operation


def get_args(func):
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
    """
    @operation
    @wraps(func)
    def wrapper(**kwargs):
        kwargs.setdefault('ctx', ctx)
        kwargs.update(deepcopy(ctx.node.properties))

        requested_inputs = {
            k: v
            for k, v
            in kwargs.items()
            if k in get_args(func)
            }

        return func(**requested_inputs)

    return wrapper
