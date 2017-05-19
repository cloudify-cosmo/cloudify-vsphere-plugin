Feature: Test attempt to create VM with network from bad relationship
  @local @server @failure @bad_vm_network @network_from_relationship
  Scenario: Fail to create a VM with bad network relationship target
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint bad-target-network-vm.yaml from template blueprints/bad-target-network-vm
    And I have inputs bad-target-network-vm-inputs.yaml from template inputs/just-linux-vm
    And I locally initialise blueprint bad-target-network-vm.yaml with inputs bad-target-network-vm-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not get
    And case sensitive install workflow errors include vsphere_network_id
    And case sensitive install workflow errors include from relationship
    And case sensitive install workflow errors include bad_node
