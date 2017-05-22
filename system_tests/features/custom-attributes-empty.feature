Feature: Test custom attributes
  @local @server @custom_attributes
  Scenario: Check empty custom attributes works
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint custom-attributes-empty.yaml from template blueprints/just-linux-vm
    And I have inputs custom-attributes-empty-inputs.yaml from template inputs/custom-attributes-empty
    And I locally initialise blueprint custom-attributes-empty.yaml with inputs custom-attributes-empty-inputs.yaml
    And I run the local install workflow
    Then VM server has custom attributes from JSON dict: {}
