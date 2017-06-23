#!/usr/bin/env python3

import json
import datetime

from azure.batch import BatchServiceClient
from azure.batch.batch_auth import SharedKeyCredentials
from azure.batch.models import (TaskAddParameter, JobAddParameter, PoolInformation, OutputFile, OutputFileDestination,
                                OutputFileUploadOptions, OutputFileUploadCondition, OutputFileBlobContainerDestination)
from azure.storage.blob import BlockBlobService, ContainerPermissions


def get_command_string(*args):
    """Generate a bash facing one-line command."""
    return "/bin/bash -c 'set -e; set -o pipefail; {}; wait'".format(';'.join(args))


def create_batch_client(settings):
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def create_storage_client(settings):
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
    build_container = job_id.replace('-', '')

    bc.job.add(JobAddParameter(job_id, PoolInformation(pool), on_all_tasks_complete=OnAllTasksComplete.terminate_job))

    sc.create_container(build_container)
    build_container_url = sc.make_blob_url(
        container_name=build_container,
        blob_name='',
        protocol='https',
        sas_token=sc.generate_container_shared_access_signature(
            container_name=build_container,
            permission=ContainerPermissions(list=True, write=True),
            expiry=(datetime.datetime.utcnow() + datetime.timedelta(days=1))))

    build_commands = [
        'git clone -b {} -- {} gitsrc'.format(settings['gitsource']['branch'], settings['gitsource']['url']),
        'cd gitsrc',
        './scripts/batch/build_all.sh',
        'ls -R ./artifacts/build'
    ]

    output_file = OutputFile('gitsrc/artifacts/build/*.*',
                             OutputFileDestination(OutputFileBlobContainerDestination(build_container_url, 'build')),
                             OutputFileUploadOptions(OutputFileUploadCondition.task_success))

    build_task = TaskAddParameter(id='build',
                                  command_line=get_command_string(*build_commands),
                                  display_name='Build all product and test code.',
                                  output_files=[output_file])

    bc.task.add(job_id, build_task)

    return job_id, build_container


def main():
    # read the settings
    with open('config.json', 'r') as fq:
        settings = json.load(fq)
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')

    bc = create_batch_client(settings)
    pool = bc.pool.get(settings['azurebatch']['pool'])
    build_job_id, build_container = schedule_build_job(pool.id, timestamp, settings)
    print('schedule build job {}. the results will be saved to container {}'.format(build_job_id, build_container))


if __name__ == '__main__':
    main()
