Feature: Test attempt to create VM with invalid standard network name
  @local @server @failure @bad_vm_network
  Scenario: Fail to create a VM with a bad standard network name
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint invalid-standard-network-name.yaml from template blueprints/just-linux-vm
    And I have inputs invalid-standard-network-name-inputs.yaml from template inputs/invalid-standard-network-name
    And I locally initialise blueprint invalid-standard-network-name.yaml with inputs invalid-standard-network-name-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include not present
    And case sensitive install workflow errors include Available networks are:
    And case insensitive install workflow errors have config value vsphere.standard_network
