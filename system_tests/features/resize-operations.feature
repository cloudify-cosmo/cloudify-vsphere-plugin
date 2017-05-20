Feature: Power operations
  @local @server @resize_operations
  Scenario: Deploy server for resize operations tests
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint resize-vm.yaml from template blueprints/just-linux-vm
    And I have inputs resize-vm-inputs.yaml from template inputs/resize-operations
    And I locally initialise blueprint resize-vm.yaml with inputs resize-vm-inputs.yaml
    And I run the local install workflow
    Then local VM server has 1 cpus
    And local VM server has 2048MB RAM

  @local @server @resize_operations
  Scenario: Giving the VM more memory and CPUs
    When I run the cloudify.interfaces.modify.resize operation with kwargs on local node server, json args: {"cpus": 2, "memory": 3072}
    Then local VM server has 2 cpus
    And local VM server has 3072MB RAM

  @local @server @resize_operations
  Scenario: Fail to give the VM too much memory (passing the boundary specified by vSphere KB 2008405)
    When I fail the cloudify.interfaces.modify.resize operation with kwargs on local node server, json args: {"cpus": 4, "memory": 4096}
    Then local VM server has 2 cpus
    And local VM server has 3072MB RAM
    And case sensitive operation errors include https://kb.vmware.com/kb/2008405
