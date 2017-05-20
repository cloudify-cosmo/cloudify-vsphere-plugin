Feature: Power operations
  @local @server @power_operations
  Scenario: Deploy server for power operations tests
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint power-vm.yaml from template blueprints/just-linux-vm
    And I have inputs power-vm-inputs.yaml from template inputs/power-operations
    And I locally initialise blueprint power-vm.yaml with inputs power-vm-inputs.yaml
    And I run the local install workflow

  @local @server @power_operations
  Scenario: Powering off the server
    Given I ensure that local VM server is powered on
    When I run the cloudify.interfaces.power.off operation on local node server
    Then local VM server power state is off

  @local @server @power_operations
  Scenario: Powering off server twice does not toggle power state
    Given I ensure that local VM server is powered on
    When I run the cloudify.interfaces.power.off operation on local node server
    And I run the cloudify.interfaces.power.off operation on local node server
    Then local VM server power state is off

  @local @server @power_operations
  Scenario: Powering on the server
    Given I ensure that local VM server is powered off
    When I run the cloudify.interfaces.power.on operation on local node server
    Then local VM server power state is on

  @local @server @power_operations
  Scenario: Powering on server twice does not toggle power state
    Given I ensure that local VM server is powered off
    When I run the cloudify.interfaces.power.on operation on local node server
    And I run the cloudify.interfaces.power.on operation on local node server
    Then local VM server power state is on

  @local @server @power_operations
  Scenario: Shutting down the server
    Given I ensure that local VM server is powered on
    When I run the cloudify.interfaces.power.shut_down operation on local node server
    Then local VM server power state is off

  @local @server @power_operations
  Scenario: Shutting down server twice does not toggle power state
    Given I ensure that local VM server is powered on
    When I run the cloudify.interfaces.power.shut_down operation on local node server
    And I run the cloudify.interfaces.power.shut_down operation on local node server
    Then local VM server power state is off

  @local @server @power_operations
  Scenario: Rebooting the server
    Given I ensure that local VM server is powered on
    And I know the last boot time of local VM server
    When I run the cloudify.interfaces.power.reboot operation on local node server
    Then local VM server power state is on
    And local VM server has been restarted during this test

  @local @server @power_operations
  Scenario: Resetting the server
    Given I ensure that local VM server is powered on
    And I know the last boot time of local VM server
    When I run the cloudify.interfaces.power.reset operation on local node server
    Then local VM server power state is on
    And local VM server has been restarted during this test
