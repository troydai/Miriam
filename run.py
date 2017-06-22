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


def schedule_build_task(job_id, settings):
    """schedule a build task in the given job. returns the container for build output and task reference."""
    bsc = create_storage_client(settings)
    container_name = job_id.replace('-', '')
    bsc.create_container(job_id.replace('-', ''))
    sas = bsc.generate_container_shared_access_signature(
        container_name, permission=ContainerPermissions(list=True, write=True),
        expiry=(datetime.datetime.utcnow() + datetime.timedelta(days=1)))
    container_url = bsc.make_blob_url(container_name, '', 'https', sas)

    print('create container', container_name)

    build_cmds = [
        'git clone -b {} -- {} gitsrc'.format(settings['gitsource']['branch'], settings['gitsource']['url']),
        'cd gitsrc',
        './scripts/batch/build_all.sh',
        'ls -R ./artifacts/build'
    ]

    output_file = OutputFile('gitsrc/artifacts/build/*.*',
                             OutputFileDestination(OutputFileBlobContainerDestination(container_url, 'build')),
                             OutputFileUploadOptions(OutputFileUploadCondition.task_success))
    build_task = TaskAddParameter(id='build',
                                  command_line=get_command_string(*build_cmds),
                                  display_name='Build all product and test code.',
                                  output_files=[output_file])

    bc = create_batch_client(settings)
    bc.task.add(job_id, build_task)
    task = bc.task.get(job_id, 'build')

    print('create build task')
    return task, container_name


def main():
    # read the settings
    with open('config.json', 'r') as fq:
        settings = json.load(fq)
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')

    # 1. schedule a job to build project and test packages
    bc = create_batch_client(settings)
    pool = bc.pool.get(settings['azurebatch']['pool'])
    print('found pool', pool.id)

    job_id = 'job-{}'.format(timestamp)
    bc.job.add(JobAddParameter(job_id, PoolInformation(pool.id), uses_task_dependencies=True))
    job = bc.job.get(job_id)

    print('create job', job.id)

    build_task, build_container = schedule_build_task(job.id, settings)
    print('schedule build task {}. the results will be saved to container {}'.format(build_task.id, build_container))


if __name__ == '__main__':
    main()
