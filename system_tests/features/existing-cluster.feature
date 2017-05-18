Feature: Existing cluster
  @local @cluster @existing
  Scenario: Use an existing cluster
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint existing-cluster.yaml from template blueprints/existing-cluster
    And I have inputs existing-cluster-inputs.yaml from template inputs/existing-cluster
    And I locally initialise blueprint existing-cluster.yaml with inputs existing-cluster-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 0 cluster(s) were created on the platform with resources prefix
    And local node cluster has runtime property vsphere_cluster_id with value starting with domain-c

  @local @cluster @existing
  Scenario: Do not delete an existing cluster
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 0 cluster(s) with resources prefix were deleted from the platform
