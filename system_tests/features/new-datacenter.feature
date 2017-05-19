Feature: Datacenter
  @local @datacenter @failure
  Scenario: Try to create a new datacenter
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint new-datacenter.yaml from template blueprints/existing-datacenter
    And I have inputs new-datacenter-inputs.yaml from template inputs/new-datacenter
    And I locally initialise blueprint new-datacenter.yaml with inputs new-datacenter-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 datacenter(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Datacenters cannot currently be created
