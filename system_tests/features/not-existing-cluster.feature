Feature: Not existing cluster
  @local @cluster @existing @failure
  Scenario: Try to use a non-existent existing cluster
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint not-existing-cluster.yaml from template blueprints/existing-cluster
    And I have inputs not-existing-cluster-inputs.yaml from template inputs/not-existing-cluster
    And I locally initialise blueprint not-existing-cluster.yaml with inputs not-existing-cluster-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 cluster(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not use existing cluster
    And case sensitive install workflow errors include no cluster by that name exists
