Feature: Test attempt to create VM with switch_distributed set incorrectly to false
  @local @server @failure @bad_vm_network
  Scenario: Fail to create a VM with switch_distributed set incorrectly to false
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint bad-switch-distributed-false.yaml from template blueprints/just-linux-vm
    And I have inputs bad-switch-distributed-false-inputs.yaml from template inputs/bad-switch-distributed-false
    And I locally initialise blueprint bad-switch-distributed-false.yaml with inputs bad-switch-distributed-false-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case insensitive install workflow errors have config value vsphere.distributed_network
    And case sensitive install workflow errors include not present
    And case sensitive install workflow errors include set the switch_distributed
    And case sensitive install workflow errors include true
