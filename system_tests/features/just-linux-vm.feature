Feature: Just a linux VM
  @local @single_node @server @linux
  Scenario: Local deployment of just a linux VM
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint just-linux-vm.yaml from template blueprints/just-linux-vm
    And I have inputs just-linux-vm-inputs.yaml from template inputs/just-linux-vm
    And I locally initialise blueprint just-linux-vm.yaml with inputs just-linux-vm-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 1 vm(s) were created on the platform with resources prefix

  @local @single_node @server @linux
  Scenario: Removing the linux VM
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 1 vm(s) with resources prefix were deleted from the platform
