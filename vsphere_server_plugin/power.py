#########
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

import cloudify.exceptions as cfy_exc

from .server import get_server_by_context
from vsphere_plugin_common.utils import op
from vsphere_plugin_common import with_server_client


@with_server_client
def _power_operation(operation_name,
                     ctx,
                     server,
                     server_client,
                     kwargs=None):
    kwargs = kwargs or {}
    server_obj = get_server_by_context(server_client, server)
    split = ' '.join(operation_name.split('_'))
    if not server_obj:
        raise cfy_exc.NonRecoverableError(
            "Cannot {action} - server doesn't exist for node: {name}".format(
                name=ctx.node.id, action=split))

    return getattr(server_client, operation_name)(server_obj,
                                                  instance=ctx.instance,
                                                  **kwargs)


@op
def power_on(max_wait_time, ctx, server, connection_config):
    return _power_operation(connection_config,
                            'start_server',
                            ctx,
                            server,
                            kwargs={'max_wait_time': max_wait_time})


@op
def power_off(max_wait_time, ctx, server, connection_config):
    return _power_operation(connection_config,
                            'stop_server',
                            ctx,
                            server,
                            kwargs={'max_wait_time': max_wait_time})


@op
def shut_down(max_wait_time, ctx, server, connection_config):
    return _power_operation(connection_config,
                            'shutdown_server_guest',
                            ctx,
                            server,
                            kwargs={'max_wait_time': max_wait_time})


@op
def reboot(max_wait_time, ctx, server, connection_config):
    return _power_operation(connection_config, 'reboot_server',
                            ctx, server,
                            kwargs={'max_wait_time': max_wait_time},)


@op
def reset(max_wait_time, ctx, server, connection_config):
    return _power_operation(connection_config,
                            'reset_server',
                            ctx,
                            server,
                            kwargs={'max_wait_time': max_wait_time})
