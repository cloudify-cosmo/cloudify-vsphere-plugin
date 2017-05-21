Feature: Test that a VM with no interfaces can be deployed
  @local @server @missing_nets
  Scenario: Test successful deployment with no attached interfaces
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint no-interfaces.yaml from template blueprints/no-interfaces
    And I have inputs no-interfaces-inputs.yaml from template inputs/no-interfaces
    And I locally initialise blueprint no-interfaces.yaml with inputs no-interfaces-inputs.yaml
    And I run the local install workflow
