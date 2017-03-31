Feature: Just a windows VM
  @local @single_node @server @windows
  Scenario: Local deployment of just a windows VM
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint just-windows-vm.yaml from template blueprints/just-windows-vm
    And I have inputs just-windows-vm-inputs.yaml from template inputs/just-windows-vm
    And I locally initialise blueprint just-windows-vm.yaml with inputs just-windows-vm-inputs.yaml
    And I run the local install workflow
    Then I know what has been changed on the platform
    # Note that due to vsphere name length limits for windows we can't use some resource prefixes with windows VMs
    And 1 vm(s) were created on the platform

  @local @single_node @server @windows
  Scenario: Removing the windows VM
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    # Note that due to vsphere name length limits for windows we can't use some resource prefixes with windows VMs
    And 1 vm(s) were deleted from the platform
