Feature: Existing datastore
  @local @datastore @existing
  Scenario: Use an existing datastore
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint existing-datastore.yaml from template blueprints/existing-datastore
    And I have inputs existing-datastore-inputs.yaml from template inputs/existing-datastore
    And I locally initialise blueprint existing-datastore.yaml with inputs existing-datastore-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    And 0 datastore(s) were created on the platform with resources prefix
    And local node datastore has runtime property vsphere_datastore_id with value starting with datastore-

  @local @datastore @existing
  Scenario: Do not delete an existing datastore
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 0 datastore(s) with resources prefix were deleted from the platform
