Feature: Test pre-existing custom attributes
  @local @server @custom_attributes @ttt
  Scenario: Check pre-existing custom attributes work
    Given I have installed cfy
    And I have installed the plugin locally
    When the custom attribute field cloudify-vsphere-plugin-tests-existing-custom-attribute is created on the platform using credentials from custom-attributes-existing-inputs.yaml
    And I have blueprint custom-attributes-existing.yaml from template blueprints/just-linux-vm
    And I have inputs custom-attributes-existing-inputs.yaml from template inputs/custom-attributes-existing
    And I have script delete_custom_attribute from template scripts/delete_custom_attribute
    And I locally initialise blueprint custom-attributes-existing.yaml with inputs custom-attributes-existing-inputs.yaml
    And I run the local install workflow
    Then VM server has custom attributes from JSON dict: {"cloudify-vsphere-plugin-tests-existing-custom-attribute": "test_attribute"}
