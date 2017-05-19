Feature: Test naming with no name set
  @local @server @naming
  Scenario: Test server naming when no name is set
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint linux-naming-no-name.yaml from template blueprints/linux-naming-no-name
    And I have inputs linux-naming-no-name-inputs.yaml from template inputs/linux-naming-no-name
    And I locally initialise blueprint linux-naming-no-name.yaml with inputs linux-naming-no-name-inputs.yaml
    And I run the local install workflow
    Then VM name for node system_tests_naming_no_name matches runtime property name
    And local linux VM from system_tests_naming_no_name node has correct name
