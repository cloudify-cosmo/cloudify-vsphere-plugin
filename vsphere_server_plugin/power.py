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

from cloudify import ctx
from cloudify.decorators import operation
import cloudify.exceptions as cfy_exc

from vsphere_plugin_common import with_server_client
from .server import get_server_by_context


@with_server_client
def _power_operation(operation_name, server_client, kwargs=None):
    if not kwargs:
        kwargs = {}
    server = get_server_by_context(server_client)
    split = ' '.join(operation_name.split('_'))
    if server is None:
        raise cfy_exc.NonRecoverableError(
            "Cannot {action} - server doesn't exist for node: {name}"
            .format(name=ctx.node.id, action=split))

    return getattr(server_client, operation_name)(server, **kwargs)


@operation
def power_on(**kwargs):
    return _power_operation('start_server')


@operation
def power_off(**kwargs):
    return _power_operation('stop_server')


@operation
def shut_down(max_wait_time, **kwargs):
    return _power_operation('shutdown_server_guest', kwargs={
        'max_wait_time': max_wait_time,
    })


@operation
def reboot(**kwargs):
    return _power_operation('reboot_server')


@operation
def reset(**kwargs):
    return _power_operation('reset_server')
