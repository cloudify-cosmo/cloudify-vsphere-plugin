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
    vsphere_host
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
before submission using tox environments, both PEP8(flake8) and PY27(nosetests).

.. code-block:: bash

    $ tox -epep8


.. code-block:: bash

    $ tox -epy27

-------
Examples
-------

For official blueprint examples using this Cloudify plugin, please see `Cloudify Community Blueprints Examples <ttps://github.com/cloudify-community/blueprint-examples/>`_.
