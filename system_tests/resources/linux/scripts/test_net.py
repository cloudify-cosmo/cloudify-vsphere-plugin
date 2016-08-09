from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from fabric.api import run, env, settings, hide

import time


def check_arp(interface, ip):
    with settings(
        hide('warnings', 'running', 'stdout', 'stderr'),
        warn_only=True,
    ):
        command = 'arping -D -f -w3 -I {interface} {ip}'.format(
            interface=interface,
            ip=ip,
        )
        result = run(command)
    if result.return_code == 0:
        return False
    elif result.return_code == 1:
        return True
    else:
        raise ValueError(
            'Could not check IP for this interface with: {command}'.format(
                command=command,
            )
        )


def get_interface(mac):
    ctx.logger.info('Getting interface name for test network interface.')
    # Show all IPs
    # then get the line with the MAC we care about and the one before it
    # The line before it contains 'LOWER_UP' if it is connected (and if not
    # then it is a problem).
    # The structure of that line is roughly:
    # <interface_number>: <interface_name>: <information about interface>
    # So we get the second element and then strip the : from it
    interface = run(
        "ip addr show | "
        "grep -B1 {mac} | "
        "grep LOWER_UP | "
        "awk '{{ print $2 }}' | "
        "sed 's/://'".format(mac=mac)
    )
    return interface


def interface_has_ip(interface, ip):
    with settings(
        hide('warnings', 'running', 'stdout', 'stderr'),
        warn_only=True,
    ):
        command = 'ip addr show {interface} | grep {ip}'.format(
            interface=interface,
            ip=ip,
        )
        result = run(command)
    if result.return_code == 0:
        return False
    elif result.return_code == 1:
        return True


def set_ip_address(interface, ip):
    for i in range(0, 30):
        if i == 0:
            ctx.logger.info('Assigning {ip} to {interface}'.format(
                interface=interface,
                ip=ip,
            ))
        elif interface_has_ip(interface, ip):
            ctx.logger.info('{ip} assigned to {interface}'.format(
                interface=interface,
                ip=ip,
            ))
            return True
        else:
            ctx.logger.info(
                '{ip} not yet assigned to {interface}. Retrying...'.format(
                    interface=interface,
                    ip=ip,
                )
            )
            time.sleep(1)
        # We do this each time as in troubleshooting of this test it has not
        # always taken effect on the first run despite a 0 return code
        with settings(
            hide('warnings', 'running', 'stdout', 'stderr'),
            warn_only=True,
        ):
            run(
                'ip addr add {ip}/24 dev {interface}'.format(
                    ip=ip,
                    interface=interface,
                )
            )


def clear_ip_address(interface, ip):
    run(
        'ip addr del {ip}/24 dev {interface}'.format(
            ip=ip,
            interface=interface,
        )
    )


def configure():
    test_network = env['test_network']
    relationship = ctx.instance.relationships[0]

    for net in relationship.target.instance.runtime_properties['networks']:
        if net['name'] == test_network:
            if net['ip'] is not None:
                raise NonRecoverableError(
                    'IP already assigned on test network',
                )
            else:
                mac_address = net['mac']

    prefix = '172.31.0.'
    interface = get_interface(mac_address)
    last_octet = 1
    ip_assigned = False

    while not ip_assigned and last_octet < 255:
        ip = prefix + str(last_octet)
        ctx.logger.info('Trying to use {ip}'.format(ip=ip))
        already_in_use = check_arp(interface, ip)
        ctx.logger.info('IP is in use? {result}'.format(result=already_in_use))
        if already_in_use:
            last_octet += 1
        else:
            ctx.logger.info('Attempting to set IP...')
            set_ip_address(interface, ip)
            # Make sure another machine didn't get our IP as we were assigning
            if check_arp(interface, ip):
                ctx.logger.warn('IP was assigned after our check, clearing...')
                ip_assigned = False
                clear_ip_address(interface, ip)
            else:
                ip_assigned = True
            if ip_assigned:
                ctx.logger.info('Succeeded! IP is now {ip}'.format(ip=ip))
            else:
                ctx.logger.warn('Failed to assign IP...')

    if not ip_assigned:
        raise NonRecoverableError('Could not assign IP address.')

    ctx.instance.runtime_properties['ping_success'] = False
    if last_octet != 1:
        # Test the networking by pinging the first IP in the range unless we
        # are on that IP
        run('ping -c4 -W1 {prefix}1'.format(prefix=prefix))
        ctx.instance.runtime_properties['ping_success'] = True
