#!/usr/bin/env python3

import sys
from datetime import datetime, timedelta


def get_command_string(*args):
    """Generate a bash facing one-line command."""
    return "/bin/bash -c 'set -e; set -o pipefail; {}; wait'".format(';'.join(args))


def create_batch_client(settings):
    from azure.batch import BatchServiceClient
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def create_storage_client(settings):
    from azure.storage.blob import BlockBlobService
    return BlockBlobService(settings['azurestorage']['account'], settings['azurestorage']['key'])


def main(settings):
    from azure.batch.models import (JobState, JobPreparationTask, JobReleaseTask, JobAddParameter, OnAllTasksComplete,
                                    ResourceFile,
                                    PoolInformation, TaskAddParameter)
    from azure.storage.blob.models import ContainerPermissions

    bc = create_batch_client(settings)
    # build_job = bc.job.get(settings['staged']['build']['job'])
    # if build_job.state != JobState.completed:
    #     print('The job {} is not completed.'.format(build_job['id']))
    #     sys.exit(1)

    # find the build container, generate read sas
    build_container = settings['staged']['build']['container']
    sc = create_storage_client(settings)
    if not sc.get_container_properties(build_container):
        print('The build container {} is not found.'.format(build_container))
        sys.exit(1)

    sas = sc.generate_container_shared_access_signature(container_name=build_container,
                                                        permission=ContainerPermissions(read=True),
                                                        expiry=(datetime.utcnow() + timedelta(days=1)))

    # upload app scripts
    for each in ('app/install.sh', 'app/status.sh'):
        sc.create_blob_from_path(container_name=build_container, blob_name=each, file_path=each)

    # create resource files
    resource_files = []
    for blob in sc.list_blobs(container_name=build_container):
        blob_url = sc.make_blob_url(build_container, blob.name, 'https', sas)
        resource_files.append(ResourceFile(blob_source=blob_url, file_path=blob.name))

    # create automation job
    prep_task = JobPreparationTask(get_command_string('./app/install.sh'),
                                   resource_files=resource_files,
                                   wait_for_success=True)

    job_id = 'test-{}'.format(datetime.utcnow().strftime('%Y%m%d-%H%M%S'))
    bc.job.add(JobAddParameter(id=job_id,
                               pool_info=PoolInformation(settings['azurebatch']['pool']),
                               display_name='Test automation job',
                               job_preparation_task=prep_task,
                               on_all_tasks_complete=OnAllTasksComplete.terminate_job))
    bc.task.add(job_id, TaskAddParameter('task-01', get_command_string('$AZ_BATCH_NODE_SHARED_DIR/app/status.sh'),
                                         'first task'))

    print('Job {} scheduled'.format(job_id))


if __name__ == '__main__':
    with open('config.json', 'r') as fq:
        import json

        local_settings = json.load(fq)

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--build-job', type=str,
                        help='The build job ID. The tasks will not be scheduled until the build job is finished.')
    parser.add_argument('--build-container', type=str,
                        help='The container which contains the test build. Command line option will overwrite config '
                             'file value.')
    arg = parser.parse_args()

    if arg.build_container:
        local_settings['staged']['build']['container'] = arg.build_container

    if arg.build_job:
        local_settings['staged']['build']['job'] = arg.build_job

    main(local_settings)
