#########
# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
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

import cloudify.exceptions as cfy_exc

from cloudify_vsphere.utils import op
from vsphere_plugin_common import with_server_client
from .server import get_server_by_context


@with_server_client
def _power_operation(
        operation_name,
        ctx,
        server,
        server_client,
        kwargs=None):
    if not kwargs:
        kwargs = {}
    server_obj = get_server_by_context(ctx, server_client, server)
    split = ' '.join(operation_name.split('_'))
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot {action} - server doesn't exist for node: {name}"
            .format(name=ctx.node.id, action=split))

    return getattr(server_client, operation_name)(server_obj, **kwargs)


@op
def power_on(ctx, server, connection_config):
    return _power_operation(connection_config, 'start_server', ctx, server)


@op
def power_off(ctx, server, connection_config):
    return _power_operation(connection_config, 'stop_server', ctx, server)


@op
def shut_down(max_wait_time, ctx, server, connection_config):
    return _power_operation(
        connection_config, 'shutdown_server_guest',
        ctx,
        server,
        kwargs={'max_wait_time': max_wait_time},
        )


@op
def reboot(ctx, server, connection_config):
    return _power_operation(connection_config, 'reboot_server', ctx, server)


@op
def reset(ctx, server, connection_config):
    return _power_operation(connection_config, 'reset_server', ctx, server)
