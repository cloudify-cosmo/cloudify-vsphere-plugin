########
# Copyright (c) 2015-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Cloudify imports
from cosmo_tester.framework.testenv import (
    initialize_without_bootstrap,
    clear_environment,
)

# This package imports


def setUp():
    initialize_without_bootstrap()


def tearDown():
    clear_environment()


def categorise_calls(call_list):
    # Expects to be called with a mock.call_args_list
    calls = {'total': 0}

    for call in call_list:
        calls['total'] += 1
        call = tuple(call)

        call_type = 'unknown'

        base_call_type = str(call[0][0]).strip("'")

        if base_call_type == 'vim.ServiceInstance:ServiceInstance':
            call_type = 'get_service_instance'
        elif base_call_type == 'vim.view.ViewManager:ViewManager':
            try:
                types = ','.join([
                    item._wsdlName
                    for item in call[0][2][1]
                ])
                call_type = 'get_{types}_list'
                call_type = call_type.format(types=types)
            except (KeyError, IndexError):
                pass
        elif base_call_type == (
            'vmodl.query.PropertyCollector:propertyCollector'
        ):
            try:
                props = ','.join([
                    item for item in
                    call[0][2][0][0].propSet[0].pathSet
                ])
                object_type = call[0][2][0][0].propSet[0].type._wsdlName
                call_type = 'get_properties_{props}_from_{object_type}'
                call_type = call_type.format(props=props,
                                             object_type=object_type)
            except (KeyError, IndexError):
                pass
        elif base_call_type.startswith('vim.view.ContainerView:session'):
            call_type = 'get_containerview_session'

        if call_type not in calls.keys():
            calls[call_type] = 1
        else:
            calls[call_type] += 1

    return calls
