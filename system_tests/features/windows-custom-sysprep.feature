Feature: Test windows custom sysprep
  @local @server @windows @custom_sysprep
  Scenario: Test windows server with custom sysprep data
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint windows-custom-sysprep.yaml from template blueprints/windows-custom-sysprep
    And I have inputs windows-custom-sysprep-inputs.yaml from template inputs/windows-custom-sysprep
    And I locally initialise blueprint windows-custom-sysprep.yaml with inputs windows-custom-sysprep-inputs.yaml
    And I run the local install workflow
    Then Windows VM server organization setting in registry retrieved with username user and password pass is Custom sysprep test
    And Windows VM server time zone in registry retrieved with username user and password pass is Eastern Standard Time
