Feature: Not existing datastore
  @local @datastore @existing @failure
  Scenario: Try to use a non-existent existing datastore
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint not-existing-datastore.yaml from template blueprints/existing-datastore
    And I have inputs not-existing-datastore-inputs.yaml from template inputs/not-existing-datastore
    And I locally initialise blueprint not-existing-datastore.yaml with inputs not-existing-datastore-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 datastore(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Could not use existing datastore
    And case sensitive install workflow errors include no datastore by that name exists
