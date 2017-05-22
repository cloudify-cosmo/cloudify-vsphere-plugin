Feature: Network name encoding
  @local @network @name_encoding
  Scenario: Confirm network name encoding functions correctly
    Given I have installed cfy
    And I have installed the plugin locally
    When I have blueprint network-slashes.yaml from template blueprints/network-slashes
    And I have inputs network-slashes-inputs.yaml from template inputs/network-slashes
    And I have script scripts/test_disk.py from template scripts/test_disk.py
    And I have script scripts/test_net.py from template scripts/test_net.py
    And I pip install https://github.com/cloudify-cosmo/cloudify-fabric-plugin/archive/1.3-build.zip
    And I locally initialise blueprint network-slashes.yaml with inputs network-slashes-inputs.yaml
    And I run the local install workflow
    Then I confirm that local output slashnet_success_1 is True
    And I confirm that local output slashnet_success_2 is True
    And I confirm that local output encnet_success_1 is True
    And I confirm that local output encnet_success_2 is True
