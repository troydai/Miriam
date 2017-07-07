import argparse


def _create_pools(args: argparse.Namespace) -> None:
    import sys
    from azure.batch.models import (PoolAddParameter, VirtualMachineConfiguration, MetadataItem, StartTask,
                                    UserIdentity, AutoUserSpecification, AutoUserScope, ElevationLevel)
    from miriam._utility import create_batch_client, get_command_string
    from miriam.verify_settings import verify_settings

    settings = verify_settings(args)
    batch_client = create_batch_client(settings)

    options = dict(((sku.id, image_ref.publisher, image_ref.offer, image_ref.sku), image_ref) for sku in
                   batch_client.account.list_node_agent_skus() for image_ref in sku.verified_image_references)

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
        batch_client.pool.add(pool)

    sys.exit(0)


def setup(subparsers) -> None:
    subparsers.add_parser('create-pools', help='Create the batch pools.').set_defaults(func=_create_pools)
