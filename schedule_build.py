#!/usr/bin/env python3

import os
import json
import datetime
import logging

from azure.batch.models import (TaskAddParameter, JobAddParameter, PoolInformation, OutputFile, OutputFileDestination,
                                OutputFileUploadOptions, OutputFileUploadCondition, OutputFileBlobContainerDestination)
from azure.storage.blob import ContainerPermissions


logger = logging.getLogger('miriam')


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


def schedule_build_job(pool, timestamp, settings):
    """
    Schedule a build job in the given pool. returns the container for build output and job reference.

    Building and running tests are two separate jobs so that the testing job can relies on job preparation tasks to
    prepare test environment. The product and test build is an essential part of the preparation. The jobs can't be
    combined because the preparation task has to be defined by the time the job is created. However neither the product
    or the test package is ready then.
    """
    from azure.batch.models import OnAllTasksComplete

    bc = create_batch_client(settings)
    sc = create_storage_client(settings)

    job_id = 'build-{}'.format(timestamp)

    bc.job.add(JobAddParameter(job_id, PoolInformation(pool), on_all_tasks_complete=OnAllTasksComplete.terminate_job))
    logger.info('Job %s is created.', job_id)

    sc.create_container('builds', fail_on_exist=False)
    build_container_url = sc.make_blob_url(
        container_name='builds',
        blob_name='',
        protocol='https',
        sas_token=sc.generate_container_shared_access_signature(
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

    bc.task.add(job_id, build_task)
    logger.info('Build task is added to job %s', job_id)

    return job_id, sc.make_blob_url(
        container_name='builds',
        blob_name=job_id,
        protocol='https',
        sas_token=sc.generate_container_shared_access_signature(
            container_name='builds',
            permission=ContainerPermissions(list=True, read=True),
            expiry=(datetime.datetime.utcnow() + datetime.timedelta(days=1))))


def main():
    # read the settings
    with open(os.path.expanduser('~/.miriam/config.json'), 'r') as fq:
        settings = json.load(fq)

    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')

    bc = create_batch_client(settings)
    pool = bc.pool.get(settings['azurebatch']['build-pool'])
    build_job_id, build_container = schedule_build_job(pool.id, timestamp, settings)
    logger.info('Build job {} is scheduled. The results will be saved to container builds.'.format(build_job_id))
    logger.info('This is a url and sas token granted with list and read access to this container. '
                'It will expire in 24 hours.')
    logger.info(build_container)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='count', help='Verbose level', default=0)
    arg = parser.parse_args()

    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][arg.verbose] if arg.verbose < 3 else logging.DEBUG
    logging.basicConfig(format='%(levelname)-8s %(name)-10s %(message)s', level=log_level)

    main()
