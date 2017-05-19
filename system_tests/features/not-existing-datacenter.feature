Feature: Not existing datacenter
  @local @datacenter @existing @failure
  Scenario: Try to use a non-existent existing datacenter
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint not-existing-datacenter.yaml from template blueprints/existing-datacenter
    And I have inputs not-existing-datacenter-inputs.yaml from template inputs/not-existing-datacenter
    And I locally initialise blueprint not-existing-datacenter.yaml with inputs not-existing-datacenter-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 datacenter(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not use existing datacenter
    And case sensitive install workflow errors include no datacenter by that name exists
