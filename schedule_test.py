#!/usr/bin/env python3

import os
import argparse
import json
import sys
import logging
from datetime import datetime, timedelta

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


def main(settings, remain_active=False):
    from azure.batch.models import (JobState, JobPreparationTask, JobReleaseTask, JobAddParameter, JobManagerTask,
                                    OnAllTasksComplete, ResourceFile, PoolInformation, TaskAddParameter,
                                    EnvironmentSetting)
    from azure.storage.blob.models import ContainerPermissions

    bc = create_batch_client(settings)
    build_job = settings['build']
    # TODO: make it wait on a build job
    # build_job = bc.job.get(settings['build'])
    # if build_job.state != JobState.completed:
    #     logger.error('The build job %s is not completed.', build_job['id'])
    #     sys.exit(1)

    # find the build container, generate read sas
    sc = create_storage_client(settings)
    if not sc.get_container_properties('builds'):
        logger.error('The build container %s is not found.', 'builds')
        sys.exit(2)

    sas = sc.generate_container_shared_access_signature(container_name='builds',
                                                        permission=ContainerPermissions(read=True),
                                                        expiry=(datetime.utcnow() + timedelta(days=1)))
    logger.info('Container %s is found and read only SAS token is generated.', 'builds')

    # create resource files
    resource_files = []
    for blob in sc.list_blobs(container_name='builds', prefix=build_job):
        blob_url = sc.make_blob_url('builds', blob.name, 'https', sas)
        file_path = blob.name[len(build_job) + 1:]
        resource_files.append(ResourceFile(blob_source=blob_url, file_path=file_path))

    if not resource_files:
        logger.error('The build %s is not found in the builds container', build_job)
        sys.exit(3)

    # create automation job
    prep_task = JobPreparationTask(get_command_string('./app/install.sh'),
                                   resource_files=resource_files,
                                   wait_for_success=True)

    env_settings = [EnvironmentSetting(name='AZURE_BATCH_KEY', value=settings['azurebatch']['key']),
                    EnvironmentSetting(name='AZURE_BATCH_ENDPOINT', value=settings['azurebatch']['endpoint'])]

    manage_task = JobManagerTask('test-creator',
                                 get_command_string('$AZ_BATCH_NODE_SHARED_DIR/app/schedule.sh'),
                                 'Automation tasks creator',
                                 kill_job_on_completion=False,
                                 environment_settings=env_settings)

    job_id = 'test-{}'.format(datetime.utcnow().strftime('%Y%m%d-%H%M%S'))
    job_complete_action = OnAllTasksComplete.no_action if remain_active else OnAllTasksComplete.terminate_job

    bc.job.add(JobAddParameter(id=job_id,
                               pool_info=PoolInformation(settings['azurebatch']['test-pool']),
                               display_name='Test automation job',
                               job_preparation_task=prep_task,
                               job_manager_task=manage_task,
                               on_all_tasks_complete=job_complete_action))

    logger.info('Job %s is created with preparation task and manager task.', job_id)


if __name__ == '__main__':
    with open(os.path.expanduser('~/.miriam/config.json'), 'r') as fq:
        local_settings = json.load(fq)

    parser = argparse.ArgumentParser()
    parser.add_argument('--build-job', type=str,
                        help='The build job ID. The tasks will not be scheduled until the build job is finished.')
    parser.add_argument('--verbose', '-v', action='count', help='Verbose level.', default=0)
    parser.add_argument('--remain-active', action='store_true', help='Keep the job active after all tasks are finished')

    arg = parser.parse_args()

    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][arg.verbose] if arg.verbose < 3 else logging.DEBUG
    logging.basicConfig(format='%(levelname)-8s %(name)-10s %(message)s', level=log_level)

    if arg.build_job:
        local_settings['build'] = arg.build_job

    main(local_settings, remain_active=arg.remain_active)
