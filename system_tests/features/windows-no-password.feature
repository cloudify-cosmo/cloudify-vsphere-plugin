Feature: Test attempt to create Windows VM with no password
  @local @server @failure @windows
  Scenario: Fail to create a Windows VM with no password set
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint windows-no-password.yaml from template blueprints/windows-no-password
    And I have inputs windows-no-password-inputs.yaml from template inputs/just-windows-vm
    And I locally initialise blueprint windows-no-password.yaml with inputs windows-no-password-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include Windows
    And case sensitive install workflow errors include password must be set
    And case sensitive install workflow errors include properties.windows_password
    And case sensitive install workflow errors include properties.agent_config.password
