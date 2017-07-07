#!/usr/bin/env python

import sys
import os.path
import yaml


def get_command_string(*args):
    return "/bin/bash -c 'set -e; set -o pipefail; {}; wait'".format(';'.join(args))


def create_batch_client(settings):
    from azure.batch import BatchServiceClient
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def create_storage_client(settings):
    from azure.storage.blob import BlockBlobService
    return BlockBlobService(settings['azurestorage']['account'], settings['azurestorage']['key'])


def create_pool(settings):
    from azure.batch.models import (PoolAddParameter, VirtualMachineConfiguration, MetadataItem, StartTask,
                                    UserIdentity, AutoUserSpecification, AutoUserScope, ElevationLevel)
    bc = create_batch_client(settings)

    options = dict(((sku.id, image_ref.publisher, image_ref.offer, image_ref.sku), image_ref) for sku in
                   bc.account.list_node_agent_skus() for image_ref in sku.verified_image_references)

    for pool_setting in settings['pools']:
        image = (pool_setting['sku'], *pool_setting['image'].split())
        vm_config = VirtualMachineConfiguration(node_agent_sku_id=pool_setting['sku'], image_reference=options[image])
        start_task = StartTask(
            command_line=get_command_string('apt-get update',
                                            'apt-get -y install python-pip',
                                            'apt-get -y install build-essential libssl-dev libffi-dev python-dev',
                                            'apt-get -y install git'),
            user_identity=UserIdentity(
                auto_user=AutoUserSpecification(scope=AutoUserScope.pool, elevation_level=ElevationLevel.admin)),
            wait_for_success=True)
        pool = PoolAddParameter(id=pool_setting['id'],
                                vm_size=pool_setting['vmsize'],
                                virtual_machine_configuration=vm_config,
                                start_task=start_task,
                                target_dedicated_nodes=int(pool_setting['dedicated']),
                                target_low_priority_nodes=int(pool_setting['low-pri']),
                                max_tasks_per_node=int(pool_setting['max-tasks']),
                                metadata=[MetadataItem('usage', pool_setting['usage'])])
        bc.pool.add(pool)

    sys.exit(0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', type=str, help='The settings file contains the credentials to the batch and '
                                                     'storage accounts. Default: ~/.miriam/config.yaml')
    parser.add_argument('--create-pool', action='store_true', help='Initiate the pool in the batch account.')
    args = parser.parse_args()

    if int(args.create_default) + int(args.verify) + int(args.create_pool) > 1:
        print('Options --create-default, --verify, and --create-pool are mutual exclusive.')
        sys.exit(1)

    if args.create_pool:
        create_pool(args.settings or os.path.expanduser('~/.miriam/config.yaml'))

    parser.print_help()
