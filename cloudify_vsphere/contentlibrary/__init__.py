# Copyright (c) 2014-2019 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import requests

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError


class ContentLibrary(object):

    def __init__(self, connection_config):
        self.config = connection_config
        response = requests.request(
            "POST", "https://{host}/rest/com/vmware/cis/session"
                    .format(host=self.config['host']),
            auth=(self.config['username'], self.config['password']),
            verify=not self.config.get('allow_insecure', False))
        response.raise_for_status()
        self.session_id = response.cookies['vmware-api-session-id']
        json_value = response.json()
        if self.session_id != json_value.get('value'):
            raise NonRecoverableError(
                "Cookies should be same: {response} != {session_id}"
                .format(response=json_value('value'),
                        session_id=self.session_id))

    def __del__(self):
        if self.session_id:
            try:
                requests.request(
                    "DELETE", "https://{host}/rest/com/vmware/cis/session"
                              .format(host=self.config['host']),
                    cookies={'vmware-api-session-id': self.session_id},
                    verify=not self.config.get('allow_insecure', False))
            except Exception as ex:
                ctx.logger.debug("Exception raised on log out: {ex}"
                                 .format(ex=repr(ex)))

    def get_content_library(self, library_name):
        # get libraries
        response = requests.request(
            "GET", "https://{host}/rest/com/vmware/content/library"
                   .format(host=self.config['host']),
            cookies={'vmware-api-session-id': self.session_id},
            verify=not self.config.get('allow_insecure', False))
        response.raise_for_status()
        value = response.json()
        if "value" not in value:
            raise NonRecoverableError("No results provided.")
        libraries = value["value"]
        ctx.logger.debug("Libraries list are {libraries}"
                         .format(libraries=repr(libraries)))

        # search our library
        for library_id in libraries:
            url = (
                "https://{host}/rest/com/vmware/content/library/"
                "id:{library_id}"
                .format(host=self.config['host'], library_id=library_id)
            )
            response = requests.request(
                "GET", url,
                cookies={'vmware-api-session-id': self.session_id},
                verify=not self.config.get('allow_insecure', False))
            response.raise_for_status()
            value = response.json()
            if "value" not in value:
                raise NonRecoverableError("No results provided.")
            library = value["value"]
            ctx.logger.debug("Library is {library}".format(library=library))
            if library.get('name') == library_name:
                return library
        else:
            raise NonRecoverableError("Library doesn't exist.")

    def get_content_item(self, library_id, template_name):
        # get list templates
        response = requests.request(
            "GET", "https://{host}/rest/com/vmware/content/library/item"
                   .format(host=self.config['host']),
            params={"library_id": library_id},
            cookies={'vmware-api-session-id': self.session_id},
            verify=not self.config.get('allow_insecure', False))
        response.raise_for_status()
        value = response.json()
        if "value" not in value:
            raise NonRecoverableError("No results provided.")
        templates = value["value"]
        ctx.logger.debug("Templates are {templates}"
                         .format(templates=templates))

        # search our template
        for template_id in templates:
            url = (
                "https://{host}/rest/com/vmware/content/library/item/"
                "id:{template_id}"
                .format(host=self.config['host'], template_id=template_id))
            response = requests.request(
                "GET", url,
                cookies={'vmware-api-session-id': self.session_id},
                verify=not self.config.get('allow_insecure', False))
            response.raise_for_status()
            value = response.json()
            if "value" not in value:
                raise NonRecoverableError("No results provided.")
            template = value["value"]
            ctx.logger.debug("Template {template}".format(template=template))
            if template.get('name') == template_name:
                return template
        else:
            raise NonRecoverableError("Template doesn't exist.")

    def deploy_content_item(self, template_id, target, parameters):
        url = (
            "https://{host}/rest/com/vmware/vcenter/ovf/library-item/"
            "id:{template_id}?~action="
            .format(host=self.config['host'], template_id=template_id)
        )
        # get deployments details
        response = requests.request(
            "POST", url + "filter",
            cookies={'vmware-api-session-id': self.session_id},
            json={"target": target},
            verify=not self.config.get('allow_insecure', False))
        response.raise_for_status()
        value = response.json()
        if "value" not in value:
            raise NonRecoverableError("No results provided.")
        deployment = value["value"]
        ctx.logger.debug("Deployment is {deployment}"
                         .format(deployment=deployment))

        # deploy
        deployment_spec = {
            "accept_all_EULA": True
        }
        deployment_spec.update(parameters)
        response = requests.request(
            "POST", url + "deploy",
            cookies={'vmware-api-session-id': self.session_id},
            json={
                "deployment_spec": deployment_spec,
                "target": target
            },
            verify=not self.config.get('allow_insecure', False))
        response.raise_for_status()
        value = response.json()
        if "value" not in value:
            raise NonRecoverableError("No results provided.")
        deployment = value["value"]
        ctx.logger.debug("Deployed {deployment}"
                         .format(deployment=deployment))
        if not deployment.get('succeeded'):
            raise NonRecoverableError("Deploy is failed: {deployment}"
                                      .format(deployment=deployment))
        return deployment
