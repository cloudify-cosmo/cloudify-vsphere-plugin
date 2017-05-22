Feature: Test new custom attributes
  @local @server @custom_attributes
  Scenario: Check new custom attributes work
    Given I have installed cfy
    And I have installed the plugin locally
    And this test will need custom attribute field cloudify-vsphere-plugin-tests-new-custom-attribute cleaning up when the run completes using credentials from custom-attributes-new-inputs.yaml
    When I have blueprint custom-attributes-new.yaml from template blueprints/just-linux-vm
    And I have inputs custom-attributes-new-inputs.yaml from template inputs/custom-attributes-new
    And I have script delete_custom_attribute from template scripts/delete_custom_attribute
    And I locally initialise blueprint custom-attributes-new.yaml with inputs custom-attributes-new-inputs.yaml
    And I run the local install workflow
    Then VM server has custom attributes from JSON dict: {"cloudify-vsphere-plugin-tests-new-custom-attribute": "test_attribute"}
