# Stdlib imports
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


def prepare_for_log(inputs):
    result = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            value = prepare_for_log(value)

        if 'password' in key:
            value = '**********'

        result[key] = value
    return result
