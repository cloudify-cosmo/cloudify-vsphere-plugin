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

import os


VSPHERE_SERVER_ID = 'vsphere_server_id'
VSPHERE_SNAPSHOT_ID = 'vsphere_snapshot_id'
PUBLIC_IP = 'public_ip'
NETWORKS = 'networks'
IP = 'ip'
VSPHERE_SERVER_HOST = 'host_server'
VSPHERE_SERVER_DATASTORE_IDS = 'datastore_ids'
VSPHERE_SERVER_DATASTORE = 'datastores'
VSPHERE_SERVER_CONNECTED_NICS = 'connected_nics'
VSPHERE_SERVER_CLUSTER_NAME = 'cluster_name'
VSPHERE_SERVER_HYPERVISOR_HOSTNAME = 'hypervisor_hostname'
VSPHERE_RESOURCE_NAME = 'name'
VSPHERE_RESOURCE_EXTERNAL = 'use_external_resource'
SERVER_RUNTIME_PROPERTIES = [VSPHERE_SERVER_ID, PUBLIC_IP, NETWORKS, IP,
                             VSPHERE_SERVER_HOST, VSPHERE_SERVER_DATASTORE_IDS,
                             VSPHERE_SERVER_DATASTORE,
                             VSPHERE_SERVER_CONNECTED_NICS,
                             VSPHERE_SERVER_CLUSTER_NAME,
                             VSPHERE_SERVER_HYPERVISOR_HOSTNAME,
                             VSPHERE_RESOURCE_NAME,
                             VSPHERE_RESOURCE_EXTERNAL]

NETWORK_NAME = 'network_name'
SWITCH_DISTRIBUTED = 'switch_distributed'
NETWORK_MTU = "mtu"
NETWORK_CIDR = "cidr"
NETWORK_CREATE_ON = "created_on"
NETWORK_STATUS = "status"
# If you change the next line you will probably break NSX integration
NETWORK_ID = 'vsphere_network_id'
NETWORK_RUNTIME_PROPERTIES = [NETWORK_NAME, SWITCH_DISTRIBUTED, NETWORK_ID,
                              NETWORK_MTU, NETWORK_CIDR, NETWORK_CREATE_ON,
                              NETWORK_STATUS]

IPPOOL_ID = 'ippool'

DATACENTER_ID = 'vsphere_datacenter_id'
DATACENTER_RUNTIME_PROPERTIES = [DATACENTER_ID]

VSPHERE_STORAGE_FILE_NAME = 'datastore_file_name'
# copy of VSPHERE_STORAGE_FILE_NAME for backward compability
VSPHERE_STORAGE_IMAGE = 'storage_image'
VSPHERE_STORAGE_VM_ID = 'attached_vm_id'
VSPHERE_STORAGE_VM_NAME = 'attached_vm_name'
VSPHERE_STORAGE_SIZE = 'storage_size'
VSPHERE_STORAGE_SCSI_ID = 'scsi_id'
VSPHERE_STORAGE_RUNTIME_PROPERTIES = [VSPHERE_STORAGE_FILE_NAME,
                                      VSPHERE_STORAGE_VM_ID,
                                      VSPHERE_STORAGE_VM_NAME,
                                      VSPHERE_STORAGE_SIZE,
                                      VSPHERE_RESOURCE_EXTERNAL,
                                      VSPHERE_STORAGE_IMAGE,
                                      DATACENTER_ID,
                                      VSPHERE_STORAGE_SCSI_ID]

DATASTORE_ID = 'vsphere_datastore_id'
DATASTORE_RUNTIME_PROPERTIES = [DATASTORE_ID]

RESOURCE_POOL_ID = 'vsphere_resource_pool_id'
RESOURCE_POOL_RUNTIME_PROPERTIES = [RESOURCE_POOL_ID]

VM_FOLDER_ID = 'vsphere_vm_folder_id'
VM_FOLDER_RUNTIME_PROPERTIES = [VM_FOLDER_ID]

HYPERVISOR_HOST_ID = 'vsphere_hypervisor_host_id'
HYPERVISOR_HOST_RUNTIME_PROPERTIES = [HYPERVISOR_HOST_ID]

CLUSTER_ID = 'vsphere_cluster_id'
CLUSTER_RUNTIME_PROPERTIES = [CLUSTER_ID]

CONTENT_ITEM_ID = "content_item_id"
CONTENT_LIBRARY_ID = "content_library_id"
CONTENT_LIBRARY_VM_NAME = "vm_name"
CONTENT_LIBRARY_PROPERTIES = [CONTENT_ITEM_ID,
                              CONTENT_LIBRARY_ID,
                              CONTENT_LIBRARY_VM_NAME,
                              VSPHERE_SERVER_ID]

TASK_CHECK_SLEEP = 15
PREFIX_RANDOM_CHARS = 3

MANAGER_PLUGIN_FILES = os.path.join('/etc', 'cloudify', 'vsphere_plugin')
DEFAULT_CONFIG_PATH = os.path.join(
    MANAGER_PLUGIN_FILES,
    'connection_config.yaml')

# Cloudify delete node action
DELETE_NODE_ACTION = "cloudify.interfaces.lifecycle.delete"

# task id for recheck
ASYNC_TASK_ID = '_task_id'
# field name for save resulted resource id
ASYNC_RESOURCE_ID = '_resource_id'

SUPPORT_DRIFT = [
    'cloudify.vsphere.nodes.Server',
    'cloudify.vsphere.nodes.WindowsServer',
    'cloudify.vsphere.nodes.IPPool',
    'cloudify.vsphere.nodes.ResourcePool'
]
