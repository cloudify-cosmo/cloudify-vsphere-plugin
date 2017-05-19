Feature: Test attempt to create distributed network on bad distributed vswitch
  @local @network @failure
  Scenario: Fail to create a distributed network on a non-existent vswitch
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint bad-dvswitch.yaml from template blueprints/just-network
    And I have inputs bad-dvswitch-inputs.yaml from template inputs/bad-dvswitch
    And I locally initialise blueprint bad-dvswitch.yaml with inputs bad-dvswitch-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 distributed_network(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include not a valid dvswitch
    And case sensitive install workflow errors include this-is-a-fake-dvswitch-name
    And case sensitive install workflow errors include The valid dvswitches are:
    And case insensitive install workflow errors have config value vsphere.distributed_vswitch
