.. highlight:: yaml

Examples
========

Server, Network, and Storage
----------------------------

::

  example_server:
      type: cloudify.vsphere.nodes.Server
      properties:
          networking:
              domain: example.com
              dns_servers: ['8.8.8.8']
              connected_networks:
                  -   name: example_management_network
                      management: true
                      switch_distributed: false
                      use_dhcp: true
                  -   name: example_external_network
                      external: true
                      switch_distributed: true
                      use_dhcp: false
                      network: 10.0.0.0/24
                      gateway: 10.0.0.1
                      ip: 10.0.0.2
                  -   name: example_network
                      switch_distributed: false
                      use_dhcp: true
              server:
                  name: example_server
                  template: example_server_template
                  cpus: 1
                  memory: 512
      relationships:
          - type: cloudify.relationships.depends_on
            target: example_network

  example_network:
      type: cloudify.vsphere.nodes.Network
      properties:
          network:
              name: example_network
              vlan_id: 101
              vswitch_name: vSwitch0
              switch_distributed: false

  example_storage:
      type: cloudify.vsphere.nodes.Storage
      properties:
          storage:
              storage_size: 1
      relationships:
          - target: example_server
            type: cloudify.vsphere.storage_connected_to_server


* ``example_server`` Creates a server. In the server 'networking' property we specified desired domain name as 'example.com', additional DNS server 8.8.8.8, and three existing networks we want to connect to: example_management_network, example_external_network and example_network.

  In the 'server' property we specified server name as example_server, vm template name as example_server_template, number of cpus as 1, and RAM as 512 MB.

* ``example_network``. Creates a network. We specified network name as example_network, network vLAN id as 101, and an existing vSwitch name we want to connect to as example_vswitch.

* ``example_storage``. Creates a virtual hard disk. We specified desired storage size as 1 GB and wish to add this storage to example_server vm.
