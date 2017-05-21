Feature: Test windows basic config
  @local @server @windows
  Scenario: Test windows server with basic config
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint windows-basic-config.yaml from template blueprints/just-windows-vm
    And I have inputs windows-basic-config-inputs.yaml from template inputs/windows-basic-config
    And I locally initialise blueprint windows-basic-config.yaml with inputs windows-basic-config-inputs.yaml
    And I run the local install workflow
    Then Windows VM server organization setting in registry retrieved with username administrator and password testpass12345 is Cloudify Test
    And Windows VM server time zone in registry retrieved with username administrator and password testpass12345 is Mountain Standard Time
