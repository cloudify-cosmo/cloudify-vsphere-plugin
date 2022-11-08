# Copyright (c) 2014-2020 Cloudify Platform Ltd. All rights reserved
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

import collections
import requests

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

from base64 import b64encode


class ContentLibrary(object):

    def __init__(self, connection_config):
        self.config = connection_config
        # we need set it empty for correct delete
        self.session_id = None
        # use header based authentication
        credentials = b64encode(
            '{0}:{1}'.format(
                self.config['username'],
                self.config['password']).encode('utf-8')).decode('ascii')
        self._call(
            "POST",
            "https://{host}/rest/com/vmware/cis/session".format(
                host=self.config['host']),
            headers={'vmware-use-header-authn': 'true',
                     'Authorization': 'Basic {0}'.format(credentials)},
            verify=not self.config.get('allow_insecure', False))

    def _call(self, *argc, **kwargs):
        response = requests.request(*argc, **kwargs)
        response.raise_for_status()
        value = response.json()
        ctx.logger.debug("Response is {value}".format(value=value))
        if "value" not in value:
            raise NonRecoverableError("No results provided.")
        if argc[0].lower() == 'post' and 'com/vmware/cis/session' in argc[1]:
            self.session_id = value["value"]
        return value["value"]

    def __del__(self):
        if self.session_id:
            try:
                self._call(
                    "DELETE",
                    "https://{host}/rest/com/vmware/cis/session".format(
                        host=self.config['host']),
                    headers={'vmware-api-session-id': self.session_id},
                    verify=not self.config.get('allow_insecure', False))
            except Exception as ex:
                ctx.logger.debug(
                    "Exception raised on log out: {ex}".format(
                        ex=repr(ex)))
        self.session_id = None

    def content_library_get(self, library_name):
        url = "https://{host}/rest/com/vmware/" \
              "content/library?~action=find".format(host=self.config['host'])
        # get libraries
        libraries = self._call(
            "POST", url,
            json={"spec": {
                "name": library_name}},
            headers={'vmware-api-session-id': self.session_id},
            verify=not self.config.get('allow_insecure', False))

        # search our library
        for library_id in libraries:
            url = "https://{host}/rest/com/vmware/content/library/" \
                  "id:{library_id}".format(
                      host=self.config['host'], library_id=library_id)
            library = self._call(
                "GET",
                url,
                headers={'vmware-api-session-id': self.session_id},
                verify=not self.config.get('allow_insecure', False))
            if library.get('name') == library_name:
                return library
        else:
            raise NonRecoverableError("Library doesn't exist.")

    def content_item_get(self, library_id, template_name):
        url = "https://{host}/rest/com/vmware/content/library/" \
              "item?~action=find".format(host=self.config['host'])
        # get list templates
        templates = self._call(
            "POST",
            url,
            json={
                "spec": {
                    "cached": True,
                    "library_id": library_id,
                    "name": template_name
                }
            },
            headers={'vmware-api-session-id': self.session_id},
            verify=not self.config.get('allow_insecure', False))

        # search our template
        for template_id in templates:
            url = "https://{host}/rest/com/vmware/content/library/" \
                  "item/id:{template_id}".format(
                      host=self.config['host'], template_id=template_id)
            template = self._call(
                "GET",
                url,
                headers={'vmware-api-session-id': self.session_id},
                verify=not self.config.get('allow_insecure', False))
            if template.get('name') == template_name:
                return template
        else:
            raise NonRecoverableError("Template doesn't exist.")

    def _cleanup_parmeters(self, v):
        """Put class as first element in dict"""
        precoded = [("@class", v["@class"])] if "@class" in v else []
        precoded += [(k, v[k]) for k in v if k != "@class"]
        return collections.OrderedDict(precoded)

    def _cleanup_specs(self, deployment_spec):
        """Clean up deployment specifiction"""
        deployment_spec["additional_parameters"] = [
            self._cleanup_parmeters(v)
            for v in deployment_spec.get("additional_parameters", [])
        ]
        return deployment_spec

    def content_item_deploy(self, template_id, target, parameters):
        url = "https://{host}/rest/com/vmware/vcenter/ovf/library-item/" \
              "id:{template_id}?~action=".format(
                  host=self.config['host'], template_id=template_id)
        # get deployments details / dump to logs
        self._call(
            "POST",
            url + "filter",
            headers={'vmware-api-session-id': self.session_id},
            json={"target": target},
            verify=not self.config.get('allow_insecure', False))

        # deploy
        deployment_spec = {
            "accept_all_EULA": True
        }
        deployment_spec.update(parameters)
        deployment_spec = self._cleanup_specs(deployment_spec)
        deployment = self._call(
            "POST",
            url + "deploy",
            headers={'vmware-api-session-id': self.session_id},
            json={
                "deployment_spec": deployment_spec,
                "target": target
            },
            verify=not self.config.get('allow_insecure', False))
        if not deployment.get('succeeded'):
            raise NonRecoverableError(
                "Deploy is failed: {deployment}".format(deployment=deployment))
        return deployment
