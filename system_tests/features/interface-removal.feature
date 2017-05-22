Feature: Test that interfaces are removed from template before deployment
  @local @server @interface_removal
  Scenario: Remove interfaces when deploying VM. Testing with VMXNet3 as we don't support attaching these.
    Given I have installed cfy
    And I have installed the plugin locally
    And linux template has at least one non-VMXNet3 interface
    When I have blueprint interface-removal.yaml from template blueprints/just-linux-vm
    And I have inputs interface-removal-inputs.yaml from template inputs/interface-removal
    And I locally initialise blueprint interface-removal.yaml with inputs interface-removal-inputs.yaml
    And I run the local install workflow
    Then deployed VM server has no non-VMXNet3 interfaces
