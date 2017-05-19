Feature: Test attempt to create VM with network from no relationship
  @local @server @failure @bad_vm_network @network_from_relationship
  Scenario: Fail to create a VM with missing network relationship target
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint no-target-network-vm.yaml from template blueprints/no-target-network-vm
    And I have inputs no-target-network-vm-inputs.yaml from template inputs/just-linux-vm
    And I locally initialise blueprint no-target-network-vm.yaml with inputs no-target-network-vm-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not find
    And case sensitive install workflow errors include relationship
    And case sensitive install workflow errors include called
    And case sensitive install workflow errors include not-a-real-node
