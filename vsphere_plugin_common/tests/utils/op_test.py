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

from mock import Mock
from pytest import fixture

from cloudify.state import current_ctx

from ...utils import op, get_args


def test_get_args_no_args():
    def func():
        ""

    assert set() == get_args(func)


def test_get_args_same_arg():
    def decorator(f):
        def wrapper(yes, no, **kwargs):
            ""
        wrapper.__wrapped__ = f
        return wrapper

    @decorator
    def func(yes):
        ""

    assert set(['yes', 'no']) == get_args(func)


def test_get_args_multiple_levels():
    def decorator(f):
        def wrapper(one, **kwargs):
            ""
        wrapper.__wrapped__ = f
        return wrapper

    def decorator_2(f):
        def wrapper(two, **kwargs):
            ""
        wrapper.__wrapped__ = f
        return wrapper

    @decorator
    @decorator_2
    def func(three):
        ""

    assert {'one', 'two', 'three'} == get_args(func)


@op
def example_operation(ctx, has, some, args):
    return ctx, has, some, args


@fixture
def ctx():
    ctx = Mock()
    ctx.instance = Mock(runtime_properties={})
    current_ctx.set(ctx)
    yield ctx
    current_ctx.clear()


def test_op_properties_only(ctx):
    obj = object()
    ctx.node.properties = {
        'has': 1,
        'some': 2,
        'args': obj,
    }

    assert (ctx, 1, 2, obj) == example_operation()


def test_op_inputs_only(ctx):
    obj = object()
    obj2 = object()

    assert (ctx, obj, obj2, obj) == example_operation(
        has=obj,
        some=obj2,
        args=obj)


def test_op_inputs_override_properties(ctx):
    original = object()
    replacement = object()
    kept = object()
    ctx.node.properties = {
        'has': 1,
        'some': kept,
        'args': original,
    }

    assert (ctx, 1, kept, replacement) == example_operation(args=replacement)


def test_op_non_supplied_args_are_None(ctx):
    ctx.node.properties = {}

    assert (ctx, None, None, None) == example_operation()
