from vsphere_plugin_common import ServerClient


def get_vsphere_client(tester_conf):
    client = ServerClient()
    cfg = {
            'host': tester_conf['vsphere.host'],
            'username': tester_conf['vsphere.username'],
            'password': tester_conf['vsphere.password'],
            'port': tester_conf['vsphere.port'],
        }
    path = tester_conf.get('vsphere.certificate_path')
    if path:
        cfg['certificate_path'] = path
    client.connect(cfg)
    return client
