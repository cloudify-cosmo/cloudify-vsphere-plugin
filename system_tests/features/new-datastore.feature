Feature: Datastore
  @local @datastore @failure
  Scenario: Try to create a new datastore
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint new-datastore.yaml from template blueprints/existing-datastore
    And I have inputs new-datastore-inputs.yaml from template inputs/new-datastore
    And I locally initialise blueprint new-datastore.yaml with inputs new-datastore-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 datastore(s) were created on the platform with resources prefix
    And install workflow errors include Datastores cannot currently be created
