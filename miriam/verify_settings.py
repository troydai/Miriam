import argparse


def verify_settings(args: argparse.Namespace) -> dict:
    import yaml
    import sys
    from miriam._utility import create_storage_client, create_batch_client

    from azure.common import AzureHttpError
    from azure.batch.models import BatchErrorException

    try:
        settings = yaml.load(args.config)
        batch_client = create_batch_client(settings)
        batch_client.pool.list()
        next(batch_client.account.list_node_agent_skus())

        storage_client = create_storage_client(settings)
        storage_client.list_containers(num_results=1)
    except AzureHttpError:
        print('Storage account setting is wrong.')
        sys.exit(1)
    except BatchErrorException:
        print('Batch account setting is wrong.')
        sys.exit(1)

    return settings


def setup(subparsers) -> None:
    subparsers.add_parser('verify-settings', help='Verify the settings file.').set_defaults(func=verify_settings)
