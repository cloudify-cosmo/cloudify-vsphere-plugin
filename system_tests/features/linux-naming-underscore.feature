Feature: Test naming with underscore for linux
  @local @server @naming
  Scenario: Test server naming with underscore
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint linux-naming-underscore.yaml from template blueprints/just-linux-vm
    And I have inputs linux-naming-underscore-inputs.yaml from template inputs/linux-naming-underscore
    And I locally initialise blueprint linux-naming-underscore.yaml with inputs linux-naming-underscore-inputs.yaml
    And I run the local install workflow
    Then VM name for node server matches runtime property name
    And local linux VM called test_name_underscore with prefix from server node has correct name
