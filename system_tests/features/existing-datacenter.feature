Feature: Existing datacenter
  @local @datacenter @existing
  Scenario: Use an existing datacenter
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint existing-datacenter.yaml from template blueprints/existing-datacenter
    And I have inputs existing-datacenter-inputs.yaml from template inputs/existing-datacenter
    And I locally initialise blueprint existing-datacenter.yaml with inputs existing-datacenter-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 0 datacenter(s) were created on the platform with resources prefix
    And local node datacenter has runtime property vsphere_datacenter_id with value starting with datacenter-

  @local @datacenter @existing
  Scenario: Do not delete an existing datacenter
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 0 datacenter(s) with resources prefix were deleted from the platform
