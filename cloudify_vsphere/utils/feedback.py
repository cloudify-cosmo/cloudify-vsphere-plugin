#########
# Copyright (c) 2017 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

# Stdlib imports
import logging
import urllib

# Third party imports

# Cloudify imports
from cloudify import ctx

# This package imports


def check_name_for_special_characters(name):
    # See https://kb.vmware.com/kb/2046088
    bad_characters = '%&*$#@!\\/:*?"<>|;\''

    name = urllib.unquote(name)

    found = []
    for bad in bad_characters:
        if bad in name:
            found.append(bad)

    if found:
        ctx.logger.warn(
            'Found characters that may cause problems in name. '
            'It is recommended that "{chars}" be avoided. '
            'In a future release such characters will be encoded when '
            'creating new entities on vSphere. '
            'Found: {found}'.format(
                chars=bad_characters,
                found=found,
            )
        )


def logger():
    try:
        logger = ctx.logger
    except RuntimeError as e:
        if 'No context' in str(e):
            logger = logging.getLogger()
        else:
            raise
    return logger


def prepare_for_log(inputs):
    result = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            value = prepare_for_log(value)

        if 'password' in key:
            value = '**********'

        result[key] = value
    return result
