from cloudify import ctx
from cloudify.state import ctx_parameters as inputs

VSPHERE_SERVER_ID = 'vsphere_server_id'


ctx.instance.runtime_properties[VSPHERE_SERVER_ID] = inputs[VSPHERE_SERVER_ID]
ctx.instance.runtime_properties['name'] = inputs['name']
