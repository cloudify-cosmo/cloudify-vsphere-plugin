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

VSPHERE_SERVER_ID = 'vsphere_server_id'
PUBLIC_IP = 'public_ip'
NETWORKS = 'networks'
IP = 'ip'
SERVER_RUNTIME_PROPERTIES = [VSPHERE_SERVER_ID, PUBLIC_IP, NETWORKS, IP]

NETWORK_NAME = 'network_name'
SWITCH_DISTRIBUTED = 'switch_distributed'
# If you change the next line you will probably break NSX integration
NETWORK_ID = 'vsphere_network_id'
NETWORK_RUNTIME_PROPERTIES = [NETWORK_NAME, SWITCH_DISTRIBUTED, NETWORK_ID]

VSPHERE_STORAGE_FILE_NAME = 'datastore_file_name'
VSPHERE_STORAGE_VM_ID = 'attached_vm_id'
VSPHERE_STORAGE_VM_NAME = 'attached_vm_name'
VSPHERE_STORAGE_SCSI_ID = 'scsi_id'
VSPHERE_STORAGE_RUNTIME_PROPERTIES = [VSPHERE_STORAGE_FILE_NAME,
                                      VSPHERE_STORAGE_VM_ID,
                                      VSPHERE_STORAGE_SCSI_ID]

DATACENTER_ID = 'vsphere_datacenter_id'
DATACENTER_RUNTIME_PROPERTIES = [DATACENTER_ID]

DATASTORE_ID = 'vsphere_datastore_id'
DATASTORE_RUNTIME_PROPERTIES = [DATASTORE_ID]

CLUSTER_ID = 'vsphere_cluster_id'
CLUSTER_RUNTIME_PROPERTIES = [CLUSTER_ID]

TASK_CHECK_SLEEP = 15
PREFIX_RANDOM_CHARS = 3
