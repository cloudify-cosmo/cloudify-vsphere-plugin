Feature: Just a distributed network
  @local @single_node @network @distributed_network
  Scenario: Local deployment of just a distributed network
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint just-distributed-network.yaml from template blueprints/just-network
    And I have inputs just-distributed-network-inputs.yaml from template inputs/just-distributed-network
    And I locally initialise blueprint just-distributed-network.yaml with inputs just-distributed-network-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 1 distributed_network(s) were created on the platform with resources prefix

  @local @single_node @network @distributed_network
  Scenario: Removing the distributed network
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 1 distributed_network(s) with resources prefix were deleted from the platform
