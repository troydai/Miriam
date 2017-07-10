import argparse

from azure.batch import BatchServiceClient
from azure.storage.blob import BlockBlobService


def generate_build_id():
    from datetime import datetime

    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    return 'build-{}'.format(timestamp)


def get_build_blob_container_url(storage_client: BlockBlobService):
    from datetime import datetime, timedelta
    from azure.storage.blob import ContainerPermissions

    storage_client.create_container('builds', fail_on_exist=False)
    return storage_client.make_blob_url(
        container_name='builds',
        blob_name='',
        protocol='https',
        sas_token=storage_client.generate_container_shared_access_signature(
            container_name='builds',
            permission=ContainerPermissions(list=True, write=True),
            expiry=(datetime.utcnow() + timedelta(days=1))))


def _create_build_job(batch_client: BatchServiceClient, storage_client: BlockBlobService, settings: dict):
    """
    Schedule a build job in the given pool. returns the container for build output and job reference.

    Building and running tests are two separate jobs so that the testing job can relies on job preparation tasks to
    prepare test environment. The product and test build is an essential part of the preparation. The jobs can't be
    combined because the preparation task has to be defined by the time the job is created. However neither the product
    or the test package is ready then.
    """
    import sys
    from azure.batch.models import (TaskAddParameter, JobAddParameter, PoolInformation, OutputFile,
                                    OutputFileDestination, OutputFileUploadOptions, OutputFileUploadCondition,
                                    OutputFileBlobContainerDestination, OnAllTasksComplete)
    from miriam._utility import get_command_string, get_logger

    remote_gitsrc_dir = 'gitsrc'
    logger = get_logger('build')
    build_id = generate_build_id()
    pool = batch_client.pool.get(next(p['id'] for p in settings['pools'] if p['usage'] == 'build'))
    if not pool:
        logger.error('Cannot find a build pool. Please check the pools list in config file.')
        sys.exit(1)

    logger.info('Creating build job %s in pool %s', build_id, pool.id)
    batch_client.job.add(JobAddParameter(id=build_id,
                                         pool_info=PoolInformation(pool.id),
                                         on_all_tasks_complete=OnAllTasksComplete.terminate_job))
    logger.info('Job %s is created.', build_id)

    build_commands = [
        'git clone -b {} -- {} gitsrc'.format(settings['gitsource']['branch'], settings['gitsource']['url']),
        f'pushd {remote_gitsrc_dir}',
        './scripts/batch/build_all.sh'
    ]

    build_container_url = get_build_blob_container_url(storage_client)

    output_file = OutputFile(f'{remote_gitsrc_dir}/artifacts/**/*.*',
                             OutputFileDestination(OutputFileBlobContainerDestination(build_container_url, build_id)),
                             OutputFileUploadOptions(OutputFileUploadCondition.task_success))

    build_task = TaskAddParameter(id='build',
                                  command_line=get_command_string(*build_commands),
                                  display_name='Build all product and test code.',
                                  output_files=[output_file])

    batch_client.task.add(build_id, build_task)
    logger.info('Build task is added to job %s', build_id)

    return build_id


def build_entry(arg: argparse.Namespace) -> None:
    import yaml
    from miriam._utility import create_storage_client, create_batch_client, get_logger

    settings = yaml.load(arg.config)
    logger = get_logger('build')

    build_job_id = _create_build_job(create_batch_client(settings),
                                     create_storage_client(settings),
                                     settings)

    logger.info('Build job {} is scheduled. The results will be saved to container builds.'.format(build_job_id))

    print(build_job_id)


def setup(subparsers) -> None:
    parser = subparsers.add_parser('build', help='Start a build job')
    parser.set_defaults(func=build_entry)
