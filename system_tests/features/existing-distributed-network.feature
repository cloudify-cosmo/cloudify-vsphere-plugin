Feature: Existing distributed network
  @local @network @existing
  Scenario: Try to use an existing distributed network
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint existing-distributed-network.yaml from template blueprints/existing-network
    And I have inputs existing-distributed-network-inputs.yaml from template inputs/existing-distributed-network
    And I locally initialise blueprint existing-distributed-network.yaml with inputs existing-distributed-network-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 0 distributed_network(s) were created on the platform with resources prefix
