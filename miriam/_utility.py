from argparse import Namespace
from azure.storage.blob import BlockBlobService
from azure.batch import BatchServiceClient


def config_logging(args: Namespace):
    import logging
    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][args.verbose] if args.verbose < 3 else logging.DEBUG
    logging.basicConfig(format='%(levelname)-8s %(name)-10s %(message)s', level=log_level)


def get_logger(scope: str = None):
    import logging
    return logging.getLogger('miriam').getChild(scope) if scope else logging.getLogger('miriam')


def get_command_string(*args):
    return "/bin/bash -c 'set -e; set -o pipefail; {}; wait'".format(';'.join(args))


def create_batch_client(settings: dict) -> BatchServiceClient:
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def create_storage_client(settings: dict) -> BlockBlobService:
    return BlockBlobService(settings['azurestorage']['account'], settings['azurestorage']['key'])
