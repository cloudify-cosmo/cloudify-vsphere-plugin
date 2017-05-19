Feature: Test naming for windows
  @local @server @naming
  Scenario: Test server naming for windows
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint windows-naming.yaml from template blueprints/just-windows-vm
    And I have inputs windows-naming-inputs.yaml from template inputs/windows-naming
    And I locally initialise blueprint windows-naming.yaml with inputs windows-naming-inputs.yaml
    And I run the local install workflow
    Then VM name for node server matches runtime property name
    And local windows VM called test-name with prefix from server node has correct name
