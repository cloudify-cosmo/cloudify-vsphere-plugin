Feature: Test that a VM with no external net can be deployed
  @local @server @missing_nets
  Scenario: Test successful deployment with no external net
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint no-external-net.yaml from template blueprints/just-linux-vm
    And I have inputs no-external-net-inputs.yaml from template inputs/no-external-net
    And I locally initialise blueprint no-external-net.yaml with inputs no-external-net-inputs.yaml
    And I run the local install workflow
