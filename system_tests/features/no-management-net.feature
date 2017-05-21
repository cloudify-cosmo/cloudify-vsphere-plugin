Feature: Test that a VM with no management net can be deployed
  @local @server @missing_nets
  Scenario: Test successful deployment with no management net
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint no-management-net.yaml from template blueprints/just-linux-vm
    And I have inputs no-management-net-inputs.yaml from template inputs/no-management-net
    And I locally initialise blueprint no-management-net.yaml with inputs no-management-net-inputs.yaml
    And I run the local install workflow
