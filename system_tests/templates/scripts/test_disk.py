# Stdlib imports

# Third party imports
from fabric.api import run, env

# Cloudify imports
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

# This package imports


def configure():
    # In case of connection related retries, see if we need to scan+mkfs
    # This will still fail in some circumstances
    # (e.g. conn failure after rescan)
    ctx.logger.info('Seeing if we need to initialise the disk..')
    mounted = run('mount').splitlines()
    mounted_paths = [mount.split()[0] for mount in mounted]
    if '/mnt' in mounted_paths:
        ctx.logger.info('Device already initialised and mounted')
    else:
        scsi_id = env['scsi_id']
        ctx.logger.info('Scanning SCSI host bus')
        run('for host in /sys/class/scsi_host/*; '
            'do echo "- - -" > ${host}/scan; '
            'done')
        ctx.logger.info(
            'Getting target device with SCSI ID: {scsi_id}'.format(
                scsi_id=scsi_id,
            )
        )
        scsi_candidates = run(
            'lsscsi *:{scsi_id}:*'.format(scsi_id=scsi_id),
        ).splitlines()
        scsi_candidates = [
            candidate for candidate in scsi_candidates
            if 'vmware' in candidate.lower() and
            'virtual disk' in candidate.lower()
        ]

        if len(scsi_candidates) != 1:
            raise NonRecoverableError(
                'Could not find a single candidate device. '
                'Found: {devices}'.format(devices=scsi_candidates)
            )
        else:
            # lsscsi output example:
            # [0:0:1:0]    disk    VMware   Virtual disk     1.0   /dev/sdb
            target_device = scsi_candidates[0].split()[-1]
            ctx.logger.info('Target device is {target}'.format(
                            target=target_device))

        ctx.logger.info('Formatting device as ext4...')
        run('mkfs.ext4 -F {device}'.format(device=target_device))
        run('mount {device} /mnt'.format(device=target_device))
        ctx.logger.info('Device formatted and mounted on /mnt')

    ctx.logger.info('Attempting to create file on device...')
    run('touch /mnt/testfile')
    ctx.logger.info('Successfully created test file on device')
