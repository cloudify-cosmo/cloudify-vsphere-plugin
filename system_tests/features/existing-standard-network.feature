Feature: Existing standard network
  @local @network @existing
  Scenario: Try to use an existing standard network
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint existing-standard-network.yaml from template blueprints/existing-network
    And I have inputs existing-standard-network-inputs.yaml from template inputs/existing-standard-network
    And I locally initialise blueprint existing-standard-network.yaml with inputs existing-standard-network-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 0 standard_network(s) were created on the platform with resources prefix
