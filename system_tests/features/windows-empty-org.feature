Feature: Test attempt to create Windows VM with empty org name
  @local @server @failure @windows
  Scenario: Fail to create a Windows VM with empty org
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint windows-empty-org.yaml from template blueprints/just-windows-vm
    And I have inputs windows-empty-org-inputs.yaml from template inputs/windows-empty-org
    And I locally initialise blueprint windows-empty-org.yaml with inputs windows-empty-org-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include must not be blank
