Feature: Test attempt to create VM with lots of bad inputs
  @local @server @failure
  Scenario: Fail to create a VM with bad inputs
    Given I have installed cfy
    And I have installed the plugin locally
    And I know what is on the platform
    When I have blueprint incorrect-inputs-vm.yaml from template blueprints/incorrect-inputs-vm
    And I have inputs incorrect-inputs-vm-inputs.yaml from template inputs/incorrect-inputs-vm
    And I locally initialise blueprint incorrect-inputs-vm.yaml with inputs incorrect-inputs-vm-inputs.yaml
    And I fail the local install workflow
    Then I know what has been changed on the platform
    And 0 vm(s) were created on the platform with resources prefix
    And case sensitive install workflow errors include No allowed hosts exist
    And case sensitive install workflow errors include No allowed clusters exist
    And case sensitive install workflow errors include No allowed datastores exist
    And case sensitive install workflow errors include Existing host(s):
    And case insensitive install workflow errors have config value vsphere.hypervisor
    And case sensitive install workflow errors include Existing cluster(s):
    And case insensitive install workflow errors have config value vsphere.cluster
    And case sensitive install workflow errors include Existing datastore(s):
    And case insensitive install workflow errors have config value vsphere.datastore
    And case sensitive install workflow errors include VM template there-is-no-template-or-vm-by-this-name could not be found
    And case sensitive install workflow errors include Datacenter no-datacenter-by-this-name-exists could not be found
    And case sensitive install workflow errors include Resource pool no-resource-pool-by-this-name-exists could not be found
