

Plugin Requirements
-------------------

Python
~~~~~~
* 2.7.x

vSphere Environment
~~~~~~~~~~~~~~~~~~~
You will require a working vSphere environment. The plugin was tested with version 6.0.

SSH Keys
~~~~~~~~

.. highlight:: bash

* You will need SSH keys generated for both the Cloudify Manager and the application VMs. If you are using the default key locations in the inputs, these can be created with the following commands::

    ssh-keygen -b2048 -N "" -q -f ~/.ssh/cloudify-manager-kp.pem
    ssh-keygen -b2048 -N "" -q -f ~/.ssh/cloudify-agent-kp.pem

Permissions on vCenter
~~~~~~~~~~~~~~~~~~~~~~

* To create and destroy virtual machines and storage:

  * On the datacenter (Must Propagate to children):

    * Datastore/Allocate Space
    * Network/Assign Network
    * Virtual Machine/Configuration/Add new disk
    * Virtual Machine/Configuration/Add or remove device
    * Virtual Machine/Configuration/Change CPU count
    * Virtual Machine/Configuration/Memory
    * Virtual Machine/Configuration/Remove disk
    * Virtual Machine/Interaction/Power On
    * Virtual Machine/Interaction/Power Off
    * Virtual Machine/Inventory/Create from existing
    * Virtual Machine/Inventory/Remove

  * On the specific resource pool:

    * Full permissions recommended

  * On the template(s) to be used

    * Virtual Machine/Provisioning/Customize
    * Virtual Machine/Provisioning/Deploy template

* To create and destroy port groups:

  * On the datacenter:

    * Host/Configuration/Network configuration
* To create and destroy distributed port groups:

  * On the datacenter:

    * dvPort group/Create
    * dvPort group/Delete


OS Templates
~~~~~~~~~~~~

* You need two OS templates within the vSphere datastores,
  one for the Cloudify Manager and one for the application VMs.
  The Cloudify Manager template must have CentOS 7 installed.
  The application VM template should accept the Cloudify agent public key for its root user.
  The Cloudify Manager template must accept the Cloudify Manager public key.
  Note that you can choose to use same template for both Cloudify Manager and the application VMs,
  in that case the shared template must accept both public keys.
* Both templates must have SSH activated and open on the firewall.
* Both templates must have VMWare tools installed. Instructions for this can be found on the [VMWare site](http://kb.vmware.com/selfservice/microsites/search.do?language=en_US&cmd=displayKC&externalId=2075048). Please note, however, that the instructions on this site give incorrect tools for importing keys (it should be using `rpm --import <key>` rather than the apt-key equivalent). After following the instructions you should also run: `chkconfig vmtoolsd on`.
* It is also necessary to install the deployPkg plugin on the VM according to [VMWare documentation](http://kb.vmware.com/selfservice/microsites/search.do?language=en_US&cmd=displayKC&externalId=2075048)
* The template should not have any network interfaces.

