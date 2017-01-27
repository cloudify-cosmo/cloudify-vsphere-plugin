
Types
=====

Node Types
----------


.. cfy:node:: cloudify.vsphere.nodes.Server

.. rubric:: Runtime properties

* ``name`` Name of the server on vsphere and in the OS
* ``ip`` Management IP address of the server (as determined by finding the IP of whichever network is set as management), or the IP of the first attached network on the server (if no management interface is set). This will be null/None if there are no attached networks.
* ``public_ip`` External IP address of server (as determined by finding the IP of whichever network is set as external), or nothing if there is no network set as external.
* ``vsphere_server_id`` Internal ID of server on vsphere (e.g. vm-1234)
* ``networks`` list of key-value details of attached networks

  * ``distributed`` Whether or not this is a distributed network
  * ``name`` The name of this network
  * ``mac`` The MAC address of the NIC on this network
  * ``ip`` The IP address assigned to the NIC on this network, or None if there is no IP

.. cfy:node:: cloudify.vsphere.nodes.WindowsServer

.. rubric:: Runtime properties

* ``name`` Name of the server on vsphere and in the OS
* ``ip`` Management IP address of the server (as determined by finding the IP of whichever network is set as management)
* ``public_ip`` External IP address of server (as determined by finding the IP of whichever network is set as external)
* ``vsphere_server_id`` Internal ID of server on vsphere (e.g. vm-1234)
* ``networks`` list of key-value details of attached networks

  * ``distributed`` Whether or not this is a distributed network
  * ``name`` The name of this network
  * ``mac`` The MAC address of the NIC on this network
  * ``ip`` The IP address assigned to the NIC on this network, or None if there is no IP


.. cfy:node:: cloudify.vsphere.nodes.Storage

.. rubric:: Runtime properties

* ``attached_vm_id`` Internal ID of attached server on vsphere (e.g. vm-1234)
* ``attached_vm_name`` Name of the attached server on vsphere and in the OS
* ``datastore_file_name`` The datastore and filename on that datastore of this virtual disk. e.g. "[Datastore-1] myserver-a12b3/myserver-a12b3_1.vmdk"
* ``scsi_id`` SCSI ID in the form of bus_id:unit_id, e.g. "0:1"


.. cfy:node:: cloudify.vsphere.nodes.Network

.. rubric:: Runtime properties

* ``network_name`` Name of the network on vsphere
* ``switch_distributed`` True if this is a distributed port group, False otherwise.


.. cfy:node:: cloudify.vsphere.nodes.Datastore



.. cfy:node:: cloudify.vsphere.nodes.Datacenter



.. cfy:node:: cloudify.vsphere.nodes.Cluster



Relationships
-------------

.. cfy:rel:: cloudify.vsphere.port_connected_to_network

.. cfy:rel:: cloudify.vsphere.port_connected_to_server

.. cfy:rel:: cloudify.vsphere.storage_connected_to_server


Data Types
----------

.. cfy:datatype:: cloudify.datatypes.vsphere.Config

.. cfy:datatype:: cloudify.datatypes.vsphere.ServerProperties

.. cfy:datatype:: cloudify.datatypes.vsphere.NetworkingProperties
