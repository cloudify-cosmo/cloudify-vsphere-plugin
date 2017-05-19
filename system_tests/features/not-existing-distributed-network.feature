Feature: Not existing distributed network
  @local @network @existing @failure
  Scenario: Try to use a non-existent existing distributed  network
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint not-existing-distributed-network.yaml from template blueprints/existing-network
    And I have inputs not-existing-distributed-network-inputs.yaml from template inputs/not-existing-distributed-network
    And I locally initialise blueprint not-existing-distributed-network.yaml with inputs not-existing-distributed-network-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 distributed_network(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not use existing distributed network
    And case sensitive install workflow errors include no distributed network by that name exists
