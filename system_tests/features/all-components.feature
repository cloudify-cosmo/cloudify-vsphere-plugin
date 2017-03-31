Feature: All components
  @local @multinode @all_components
  Scenario: Local deployment of all components
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint all-components.yaml from template blueprints/all-components
    And I have inputs all-components-inputs.yaml from template inputs/all-components
    And I have script scripts/test_disk.py from template scripts/test_disk.py
    And I have script scripts/test_net.py from template scripts/test_net.py
    And I pip install https://github.com/cloudify-cosmo/cloudify-fabric-plugin/archive/1.3-build.zip
    And I locally initialise blueprint all-components.yaml with inputs all-components-inputs.yaml
    And I run the local install workflow
    Then I confirm that local output distnetworktest_success_1 is True
    And I confirm that local output distnetworktest_success_2 is True
    And I confirm that local output standardnetworktest_success_1 is True
    And I confirm that local output standardnetworktest_success_2 is True
    And I know what has been changed on the platform
    And 2 vm(s) were created on the platform with resources prefix
    And 1 standard_network(s) were created on the platform with resources prefix
    And 1 distributed_network(s) were created on the platform with resources prefix

  @local @multinode @all_components
  Scenario: Local undeployment of all components
    Given no tests have failed in this feature
    And I know what is on the platform
    When I run the local uninstall workflow
    Then I know what has been changed on the platform
    And 2 vm(s) with resources prefix were deleted from the platform
    And 1 standard_network(s) with resources prefix were deleted from the platform
    And 1 distributed_network(s) with resources prefix were deleted from the platform
