Feature: Test attempt to create Windows VM with too long org name
  @local @server @failure @windows
  Scenario: Fail to create a Windows VM with too long org
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint windows-too-long-org.yaml from template blueprints/just-windows-vm
    And I have inputs windows-too-long-org-inputs.yaml from template inputs/windows-too-long-org
    And I locally initialise blueprint windows-too-long-org.yaml with inputs windows-too-long-org-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include 64
