# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
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

from __future__ import division

# Stdlib imports
from functools import wraps

# Third party imports

# Cloudify imports
from cloudify import ctx
from cloudify import context

# This package imports
from .constants import (
    ASYNC_TASK_ID,
    DELETE_NODE_ACTION,
)
from .clients import VsphereClient  # noqa
from .clients.server import ServerClient
from .clients.network import NetworkClient
from .clients.storage import StorageClient, RawVolumeClient


def remove_runtime_properties():
    # cleanup runtime properties
    # need to convert generaton to list, python 3
    for prop_key in list(ctx.instance.runtime_properties.keys()):
        del ctx.instance.runtime_properties[prop_key]
    # save flag as current state before external call
    ctx.instance.update()


def run_deferred_task(client, instance=None):
    instance = instance or ctx.instance
    if instance.runtime_properties.get(ASYNC_TASK_ID):
        client._wait_for_task(instance)


def _with_client(client_name, client):
    def decorator(f):
        @wraps(f)
        def wrapper(connection_config, *args, **kwargs):
            kwargs[client_name] = client().get(config=connection_config)
            if not hasattr(f, '__wrapped__'):
                # don't pass connection_config to the real operation
                kwargs.pop('connection_config', None)

            try:
                # check unfinished tasks
                if ctx.type == context.NODE_INSTANCE:
                    run_deferred_task(client=kwargs[client_name])
                elif ctx.type == context.RELATIONSHIP_INSTANCE:
                    run_deferred_task(client=kwargs[client_name],
                                      instance=ctx.source.instance)
                    run_deferred_task(client=kwargs[client_name],
                                      instance=ctx.target.instance)

                # run real task
                result = f(*args, **kwargs)
                # in delete action
                current_action = ctx.operation.name
                if current_action == DELETE_NODE_ACTION and \
                        ctx.type == context.NODE_INSTANCE:
                    # no retry actions
                    if not ctx.instance.runtime_properties.get(ASYNC_TASK_ID):
                        ctx.logger.info('Cleanup resource.')
                        # cleanup runtime
                        remove_runtime_properties()
                # return result
                return result
            except Exception:
                raise
        wrapper.__wrapped__ = f
        return wrapper
    return decorator


with_server_client = _with_client('server_client', ServerClient)
with_network_client = _with_client('network_client', NetworkClient)
with_storage_client = _with_client('storage_client', StorageClient)
with_rawvolume_client = _with_client('rawvolume_client', RawVolumeClient)
