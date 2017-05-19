Feature: Test naming for linux
  @local @server @naming
  Scenario: Test server naming
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint linux-naming.yaml from template blueprints/just-linux-vm
    And I have inputs linux-naming-inputs.yaml from template inputs/linux-naming
    And I locally initialise blueprint linux-naming.yaml with inputs linux-naming-inputs.yaml
    And I run the local install workflow
    Then VM name for node server matches runtime property name
    And local linux VM called test-name with prefix from server node has correct name
