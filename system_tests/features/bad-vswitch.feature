Feature: Test attempt to create standard network on bad standard vswitch
  @local @network @failure
  Scenario: Fail to create a standard network on a non-existent vswitch
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint bad-vswitch.yaml from template blueprints/just-network
    And I have inputs bad-vswitch-inputs.yaml from template inputs/bad-vswitch
    And I locally initialise blueprint bad-vswitch.yaml with inputs bad-vswitch-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 standard_network(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include not a valid vswitch
    And case sensitive install workflow errors include this-is-a-fake-vswitch-name
    And case sensitive install workflow errors include The valid vswitches are:
    And case insensitive install workflow errors have config value vsphere.standard_vswitch
