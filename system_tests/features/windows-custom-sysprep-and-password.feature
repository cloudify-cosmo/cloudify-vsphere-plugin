Feature: Test attempt to create Windows VM with both password and custom sysprep
  @local @server @failure @windows
  Scenario: Fail to create a Windows VM with password and custom sysprep set
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint windows-custom-sysprep-and-password.yaml from template blueprints/windows-custom-sysprep-and-password
    And I have inputs windows-custom-sysprep-and-password-inputs.yaml from template inputs/just-windows-vm
    And I locally initialise blueprint windows-custom-sysprep-and-password.yaml with inputs windows-custom-sysprep-and-password-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include custom_sysprep
    And case sensitive install workflow errors include but
    And case sensitive install workflow errors include windows_password
