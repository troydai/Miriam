import os
import argparse


def _create_default_config(args: argparse.Namespace) -> None:
    import yaml

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

    yaml.safe_dump(settings, args.output, indent=2, encoding='utf-8', default_flow_style=False)


def setup(subparsers) -> None:
    parser = subparsers.add_parser('create-default', help='Create a default config file as template.')
    parser.add_argument('--output', help='The path where the default config file is saved.',
                        type=argparse.FileType('w'),
                        default=open(os.path.join(os.getcwd(), 'default-config.yaml'), 'w'))
    parser.set_defaults(func=_create_default_config)
