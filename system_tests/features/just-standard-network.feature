Feature: Just a standard network
  @local @single_node @network @standard_network
  Scenario: Local deployment of just a standard network
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint just-standard-network.yaml from template blueprints/just-network
    And I have inputs just-standard-network-inputs.yaml from template inputs/just-standard-network
    And I locally initialise blueprint just-standard-network.yaml with inputs just-standard-network-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 1 standard_network(s) were created on the platform with resources prefix

  @local @single_node @network @standard_network
  Scenario: Removing the standard network
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 1 standard_network(s) with resources prefix were deleted from the platform
