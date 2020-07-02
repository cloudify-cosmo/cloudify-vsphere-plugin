########
# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
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


import os
import pytest

from ecosystem_tests.dorkl import (
    basic_blueprint_test,
    cleanup_on_failure,
    prepare_test
)

SECRETS_TO_CREATE = {
    'vsphere_username': False,
    'vsphere_password': False,
    'vsphere_host': False,
    'vsphere_port': False,
    'vsphere_datacenter_name': False,
    'vsphere_resource_pool_name': False,
    'vsphere_auto_placement': False,
    'centos_template': False,
    'vsphere_private_key': True,
    'vsphere_public_key': True
}

prepare_test(secrets=SECRETS_TO_CREATE, use_vpn=True)

blueprint_list = ['examples/blueprint-examples/virtual-machine/vsphere.yaml']


@pytest.fixture(scope='function', params=blueprint_list)
def blueprint_examples(request):
    dirname_param = os.path.dirname(request.param).split('/')[-1:][0]
    try:
        basic_blueprint_test(
            request.param,
            dirname_param,
            inputs='resource_prefix=kube-{0}'.format(
                os.environ['CIRCLE_BUILD_NUM']),
            use_vpn=True)
    except:
        cleanup_on_failure(dirname_param)
        raise


def test_blueprints(blueprint_examples):
    assert blueprint_examples is None
