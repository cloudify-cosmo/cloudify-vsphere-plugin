=======================
Cloudify vSphere Plugin
=======================

---------------
Plugin overview
---------------

Cloudify plugin for deploying management node over vSphere environment

------------
Installation
------------

Stable release::
.. code-block:: bash

    $ pip install -r requirements.txt
    $ python setup.py install

Development::
.. code-block:: bash

    $ virtualenv .venv & source .venv/bin/activate
    $ pip install -r dev-requirements.txt -r test-requirements.txt

-------------------------------------------
Usage example.Bootstrapping management node
-------------------------------------------

First of all please take time to create your own inputs.yaml or edit inputs.yaml.template
with correct credentials and necessary info::

    vsphere_username
    vsphere_password
    vsphere_url
    vsphere_datacenter_name
    manager_server_template
    manager_server_cpus
    manager_server_memory
    manager_server_user
    manager_server_user_home
    management_network_name
    management_network_switch_distributed
    external_network_name
    external_network_switch_distributed
    manager_private_key_path
    agent_private_key_path
    agents_user
    resources_prefix

.. code-block:: bash

    $ cfy bootstrap -p manager_blueprint/vsphere-manager-blueprint.yaml -i manager_blueprint/inputs.yaml

-------
Testing
-------

With respect to Cloudify development and contribution documentation each patch should be tested
before submission using tox environments, both PEP8 and PY27.

.. code-block:: bash

    $ tox -epep8


Enabled PEP8 rules::

    E123: closing bracket does not match indentation of opening bracket's line
    E101: commit message body and code inline comments checks
    H233: python 3.x incompatible use of print operator
    H234: deprecation warnings (assertEquals is deprecated, use assertEqual)
    E226: missing whitespace around arithmetic operator
    H301: one import per line
    H302: import only modules
    H306: sort imports in alphabetic order

.. code-block:: bash

    $ tox -epy27
