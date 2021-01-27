# Copyright (c) 2019-2020 Cloudify Platform Ltd. All rights reserved
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

# Stdlib imports

# Third party imports
from pyVmomi import vim

# Cloudify imports
from cloudify.exceptions import NonRecoverableError

# This package imports
from vsphere_plugin_common.utils import op
from vsphere_plugin_common.utils import find_rels_by_type
from vsphere_plugin_common import with_server_client
from vsphere_plugin_common.constants import RESOURCE_POOL_ID

RESOURCE_POOL_CONTAINED_IN = \
    'cloudify.relationships.vsphere.resource_pool_contained_in'


def _get_pool_spec(pool_spec, old_config=None):
    spec = vim.ResourceConfigSpec()
    if old_config:
        spec.memoryAllocation = old_config.memoryAllocation
        spec.cpuAllocation = old_config.cpuAllocation
    else:
        # initialize with default
        spec.memoryAllocation = vim.ResourceAllocationInfo()
        spec.memoryAllocation.limit = -1
        spec.memoryAllocation.reservation = 0
        spec.memoryAllocation.expandableReservation = True
        spec.memoryAllocation.shares = vim.SharesInfo()
        spec.memoryAllocation.shares.shares = 163840
        spec.memoryAllocation.shares.level = 'normal'
        spec.cpuAllocation = vim.ResourceAllocationInfo()
        spec.cpuAllocation.limit = -1
        spec.cpuAllocation.reservation = 0
        spec.cpuAllocation.expandableReservation = True
        spec.cpuAllocation.shares = vim.SharesInfo()
        spec.cpuAllocation.shares.shares = 4000
        spec.cpuAllocation.shares.level = 'normal'

    # override values given the input
    if 'memoryAllocation' in pool_spec:
        if 'limit' in pool_spec.get('memoryAllocation'):
            spec.memoryAllocation.limit = \
                pool_spec.get('memoryAllocation').get('limit')
        if 'reservation' in pool_spec.get('memoryAllocation'):
            spec.memoryAllocation.reservation = \
                pool_spec.get('memoryAllocation').get('reservation')
        if 'expandableReservation' in pool_spec.get('memoryAllocation'):
            spec.memoryAllocation.expandableReservation = \
                pool_spec.get('memoryAllocation').get('expandableReservation')
        if 'shares' in pool_spec.get('memoryAllocation'):
            shares = pool_spec.get('memoryAllocation').get('shares')
            if 'shares' in shares:
                spec.memoryAllocation.shares.shares = shares.get('shares')
            if 'level' in shares:
                spec.memoryAllocation.shares.level = shares.get('level')

    if 'cpuAllocation' in pool_spec:
        if 'limit' in pool_spec.get('cpuAllocation'):
            spec.cpuAllocation.limit = \
                pool_spec.get('cpuAllocation').get('limit')
        if 'reservation' in pool_spec.get('cpuAllocation'):
            spec.cpuAllocation.reservation = \
                pool_spec.get('cpuAllocation').get('reservation')
        if 'expandableReservation' in pool_spec.get('cpuAllocation'):
            spec.cpuAllocation.expandableReservation = \
                pool_spec.get('cpuAllocation').get('expandableReservation')
        if 'shares' in pool_spec.get('cpuAllocation'):
            shares = pool_spec.get('cpuAllocation').get('shares')
            if 'shares' in shares:
                spec.cpuAllocation.shares.shares = shares.get('shares')
            if 'level' in shares:
                spec.cpuAllocation.shares.level = shares.get('level')

    return spec


@op
@with_server_client
def create(ctx, server_client, name, use_external_resource, host_name,
           cluster_name, pool_spec):
    if use_external_resource:
        vmware_resource = server_client.get_resource_pool_by_name(name)

        if not vmware_resource:
            raise NonRecoverableError(
                'Could not use existing resource_pool "{name}" as no '
                'resource_pool by that name exists!'.format(
                    name=name,
                )
            )

        ctx.instance.runtime_properties[RESOURCE_POOL_ID] = vmware_resource.id
    else:
        vmware_resource = None
        spec = _get_pool_spec(pool_spec)
        resource_pools_from_rels = find_rels_by_type(
            ctx.instance, RESOURCE_POOL_CONTAINED_IN)
        # create resource pool on host
        if host_name:
            ctx.logger.info(
                'creating resource_pool on host {0}'.format(host_name))
            vmware_resource = \
                server_client.create_resource_pool(name, host_name,
                                                   vim.ComputeResource, spec)
        # create resource pool on cluster
        elif cluster_name:
            ctx.logger.info(
                'creating resource_pool on cluster {0}'.format(cluster_name))
            vmware_resource = \
                server_client.create_resource_pool(name, cluster_name,
                                                   vim.ClusterComputeResource,
                                                   spec)
        # check if contained in resource pool
        elif len(resource_pools_from_rels) == 1:
            ctx.logger.info(
                'creating resource_pool inside another resource pool')
            resource_pool_from_rel = resource_pools_from_rels[0]
            parent_id = \
                resource_pool_from_rel.target.instance.runtime_properties.get(
                    RESOURCE_POOL_ID)
            vmware_resource = \
                server_client.create_contained_resource_pool(name, parent_id,
                                                             spec)
        if not vmware_resource:
            raise NonRecoverableError('resource pool was not created.')

        ctx.instance.runtime_properties[RESOURCE_POOL_ID] = \
            vmware_resource._moId


@op
@with_server_client
def delete(ctx, server_client, name, use_external_resource, **_):
    if use_external_resource:
        ctx.logger.info(
            'Not deleting existing resource_pool: {name}'.format(
                name=name,
            )
        )
    else:
        server_client.delete_resource_pool(name)


@op
@with_server_client
def update_resource_pool(ctx, server_client, name, pool_spec, **_):
    vmware_resource = server_client.get_resource_pool_by_name(name)

    if not vmware_resource:
        ctx.logger.debug('resource pool was not found to update.')
        return

    spec = _get_pool_spec(pool_spec, vmware_resource.obj.config)
    vmware_resource.obj.UpdateConfig(name, spec)
