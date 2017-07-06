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


def create_default():
    settings = {
        "gitsource": {
            "url": "the url to the git repository",
            "branch": "master"
        },
        "azurebatch": {
            "account": "the batch account name",
            "key": "the batch account key",
            "endpoint": "the batch account endpoint"
        },
        "azurestorage": {
            "account": "the storage account name",
            "key": "the storage account key"
        },
        "automation": {
            "account": "the service principal for running azure cli live test",
            "key": "the service principal's password",
            "tenant": "the service principal's tenant"
        },
        "pools": [
            {
                'usage': 'usage',
                'id': 'pool id',
                'sku': 'batch node agent sku',
                'image': 'publisher offer sku',
                'vmsize': 'size',
                'dedicated': 'number of dedicated node',
                'low-pri': 'number of low-priority node',
                'max-tasks': 'number of max tasks per node'
            }
        ]
    }

    with open('default.config.yaml', 'w') as fq:
        yaml.safe_dump(settings, fq, indent=2, encoding='utf-8', default_flow_style=False)


def verify(setting_file_path):
    from azure.common import AzureHttpError
    from azure.batch.models import BatchErrorException

    try:
        with open(setting_file_path, 'r') as fq:
            settings = yaml.load(fq)
            batch_client = create_batch_client(settings)
            batch_client.pool.list()
            next(batch_client.account.list_node_agent_skus())

            storage_client = create_storage_client(settings)
            storage_client.list_containers(num_results=1)
    except IOError:
        print('Failed to read file {}'.format(setting_file_path))
        sys.exit(1)
    except AzureHttpError:
        print('Storage account setting is wrong.')
        sys.exit(1)
    except BatchErrorException:
        print('Batch account setting is wrong.')
        sys.exit(1)

    return settings


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', type=str, help='The settings file contains the credentials to the batch and '
                                                     'storage accounts. Default: ~/.miriam/config.yaml')
    parser.add_argument('--create-default', action='store_true',
                        help='Create a default configuration file at current location')
    parser.add_argument('--verify', action='store_true', help='Verify the settings file.')
    parser.add_argument('--create-pool', action='store_true', help='Initiate the pool in the batch account.')
    args = parser.parse_args()

    if int(args.create_default) + int(args.verify) + int(args.create_pool) > 1:
        print('Options --create-default, --verify, and --create-pool are mutual exclusive.')
        sys.exit(1)

    if args.create_default:
        create_default()

    if args.verify:
        verify(args.settings or os.path.expanduser('~/.miriam/config.yaml'))
        sys.exit(0)

    if args.create_pool:
        create_pool(verify(args.settings or os.path.expanduser('~/.miriam/config.yaml')))

    parser.print_help()
