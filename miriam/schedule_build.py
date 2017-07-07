import datetime
import argparse

from ._utility import create_storage_client, create_batch_client, get_command_string, get_logger


def _create_build_job(pool, timestamp, settings):
    """
    Schedule a build job in the given pool. returns the container for build output and job reference.

    Building and running tests are two separate jobs so that the testing job can relies on job preparation tasks to
    prepare test environment. The product and test build is an essential part of the preparation. The jobs can't be
    combined because the preparation task has to be defined by the time the job is created. However neither the product
    or the test package is ready then.
    """
    from azure.batch.models import (TaskAddParameter, JobAddParameter, PoolInformation, OutputFile,
                                    OutputFileDestination, OutputFileUploadOptions, OutputFileUploadCondition,
                                    OutputFileBlobContainerDestination, OnAllTasksComplete)
    from azure.storage.blob import ContainerPermissions

    logger = get_logger('build')

    batch_client = create_batch_client(settings)
    storage_client = create_storage_client(settings)

    job_id = 'build-{}'.format(timestamp)

    batch_client.job.add(
        JobAddParameter(job_id, PoolInformation(pool), on_all_tasks_complete=OnAllTasksComplete.terminate_job))
    logger.info('Job %s is created.', job_id)

    storage_client.create_container('builds', fail_on_exist=False)
    build_container_url = storage_client.make_blob_url(
        container_name='builds',
        blob_name='',
        protocol='https',
        sas_token=storage_client.generate_container_shared_access_signature(
            container_name='builds',
            permission=ContainerPermissions(list=True, write=True),
            expiry=(datetime.datetime.utcnow() + datetime.timedelta(days=1))))
    logger.info('Container %s and corresponding write SAS is created.', 'builds')

    build_commands = [
        'git clone -b {} -- {} gitsrc'.format(settings['gitsource']['branch'], settings['gitsource']['url']),
        'cd gitsrc',
        './scripts/batch/build_all.sh'
    ]

    output_file = OutputFile('gitsrc/artifacts/**/*.*',
                             OutputFileDestination(OutputFileBlobContainerDestination(build_container_url, job_id)),
                             OutputFileUploadOptions(OutputFileUploadCondition.task_success))

    build_task = TaskAddParameter(id='build',
                                  command_line=get_command_string(*build_commands),
                                  display_name='Build all product and test code.',
                                  output_files=[output_file])

    batch_client.task.add(job_id, build_task)
    logger.info('Build task is added to job %s', job_id)

    return job_id, storage_client.make_blob_url(
        container_name='builds',
        blob_name=job_id,
        protocol='https',
        sas_token=storage_client.generate_container_shared_access_signature(
            container_name='builds',
            permission=ContainerPermissions(list=True, read=True),
            expiry=(datetime.datetime.utcnow() + datetime.timedelta(days=1))))


def _build_entry(arg: argparse.Namespace) -> None:
    import yaml

    settings = yaml.load(arg.config)
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    logger = get_logger('build')
    batch_client = create_batch_client(settings)

    build_pool = next(p['id'] for p in settings['pools'] if p['usage'] == 'build')
    pool = batch_client.pool.get(build_pool)
    build_job_id, _ = _create_build_job(pool.id, timestamp, settings)

    logger.info('Build job {} is scheduled. The results will be saved to container builds.'.format(build_job_id))

    print(build_job_id)


def setup_arguments(subparsers) -> None:
    parser = subparsers.add_parser('build', help='Start a build job')
    parser.add_argument('--test', action='store_true', help='Run tests against the build')
    parser.add_argument('--live', action='store_true', help='Run tests live')
    parser.set_defaults(func=_build_entry)
