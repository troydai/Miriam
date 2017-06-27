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


def main(build_id: str, settings: dict, remain_active: bool = False, run_live: bool = False):
    from azure.batch.models import (JobState, JobPreparationTask, JobReleaseTask, JobAddParameter, JobManagerTask,
                                    OnAllTasksComplete, ResourceFile, PoolInformation, TaskAddParameter,
                                    EnvironmentSetting)
    from azure.storage.blob.models import ContainerPermissions

    bc = create_batch_client(settings)

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
    for blob in sc.list_blobs(container_name='builds', prefix=build_id):
        blob_url = sc.make_blob_url('builds', blob.name, 'https', sas)
        file_path = blob.name[len(build_id) + 1:]
        resource_files.append(ResourceFile(blob_source=blob_url, file_path=file_path))

    if not resource_files:
        logger.error('The build %s is not found in the builds container', build_id)
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

    # create output storage container
    output_container_name = 'output-{}'.format(job_id)
    sc.create_container(container_name=output_container_name)
    output_container_url = sc.make_blob_url(
        container_name=output_container_name,
        blob_name='',
        protocol='https',
        sas_token=sc.generate_container_shared_access_signature(
            container_name=output_container_name,
            permission=ContainerPermissions(list=True, write=True),
            expiry=(datetime.utcnow() + timedelta(days=1))))

    # create automation job
    job_complete_action = OnAllTasksComplete.no_action if remain_active else OnAllTasksComplete.terminate_job

    job_environment = [EnvironmentSetting(name='AUTOMATION_OUTPUT_CONTAINER', value=output_container_url)]
    if run_live:
        job_environment.append(EnvironmentSetting(name='AZURE_TEST_RUN_LIVE', value='True'))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_NAME', value=settings['automation']['account']))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_PASSWORD', value=settings['automation']['key']))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_TENANT', value=settings['automation']['tenant']))

    bc.job.add(JobAddParameter(id=job_id,
                               pool_info=PoolInformation(settings['azurebatch']['test-pool']),
                               display_name='Automation on build {}. Live: {}'.format(build_id, run_live),
                               common_environment_settings=job_environment,
                               job_preparation_task=prep_task,
                               job_manager_task=manage_task,
                               on_all_tasks_complete=job_complete_action))

    logger.info('Job %s is created with preparation task and manager task.', job_id)

if __name__ == '__main__':
    with open(os.path.expanduser('~/.miriam/config.json'), 'r') as fq:
        local_settings = json.load(fq)

    parser = argparse.ArgumentParser()
    parser.add_argument('job_id', help='The ID of the build to be testd.')
    parser.add_argument('--verbose', '-v', action='count', help='Verbose level.', default=0)
    parser.add_argument('--remain-active', action='store_true', help='Keep the job active after all tasks are finished')
    parser.add_argument('--live', action='store_true', help='Run all the tests live')

    arg = parser.parse_args()

    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][arg.verbose] if arg.verbose < 3 else logging.DEBUG
    logging.basicConfig(format='%(levelname)-6s %(name)-10s %(message)s', level=log_level)

    main(arg.job_id, local_settings, remain_active=arg.remain_active, run_live=arg.live)
