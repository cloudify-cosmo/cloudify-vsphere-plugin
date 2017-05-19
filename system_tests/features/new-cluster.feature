Feature: Cluster
  @local @cluster @failure
  Scenario: Try to create a new cluster
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint new-cluster.yaml from template blueprints/existing-cluster
    And I have inputs new-cluster-inputs.yaml from template inputs/new-cluster
    And I locally initialise blueprint new-cluster.yaml with inputs new-cluster-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 cluster(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Clusters cannot currently be created
