#!/usr/bin/env python3

from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from azure.storage.blob import BlockBlobService
from miriam._utility import get_logger, get_command_string, create_batch_client, create_storage_client


def _list_build_resource_files(storage_client: BlockBlobService, build_id: str):
    """ List the files belongs to the target build in the build blob container """
    import sys
    from azure.storage.blob.models import ContainerPermissions
    from azure.batch.models import ResourceFile

    logger = get_logger('test')

    if not storage_client.get_container_properties('builds'):
        logger.error('The build container %s is not found.', 'builds')
        sys.exit(2)

    sas = storage_client.generate_container_shared_access_signature(container_name='builds',
                                                                    permission=ContainerPermissions(read=True),
                                                                    expiry=(datetime.utcnow() + timedelta(days=1)))
    logger.info('Container %s is found and read only SAS token is generated.', 'builds')

    resource_files = []
    for blob in storage_client.list_blobs(container_name='builds', prefix=build_id):
        blob_url = storage_client.make_blob_url('builds', blob.name, 'https', sas)
        file_path = blob.name[len(build_id) + 1:]
        resource_files.append(ResourceFile(blob_source=blob_url, file_path=file_path))

    if not resource_files:
        logger.error('The build %s is not found in the builds container', build_id)
        sys.exit(3)

    return resource_files


def _create_output_container_folder(storage_client: BlockBlobService, job_id: str):
    """ Create output storage container """
    from azure.storage.blob.models import ContainerPermissions

    output_container_name = 'output-{}'.format(job_id)
    storage_client.create_container(container_name=output_container_name)

    return storage_client.make_blob_url(
        container_name=output_container_name,
        blob_name='',
        protocol='https',
        sas_token=storage_client.generate_container_shared_access_signature(
            container_name=output_container_name,
            permission=ContainerPermissions(list=True, write=True),
            expiry=(datetime.utcnow() + timedelta(days=1))))


def _create_test_job(build_id: str, settings: dict, remain_active: bool = False, run_live: bool = False):
    from azure.batch.models import (JobPreparationTask, JobAddParameter, JobManagerTask, OnAllTasksComplete,
                                    PoolInformation, EnvironmentSetting)

    logger = get_logger('test')
    batch_client = create_batch_client(settings)
    storage_client = create_storage_client(settings)

    # create automation job
    resource_files = _list_build_resource_files(storage_client, build_id)

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

    output_container_url = _create_output_container_folder(storage_client, job_id)

    job_environment = [EnvironmentSetting(name='AUTOMATION_OUTPUT_CONTAINER', value=output_container_url)]
    if run_live:
        job_environment.append(EnvironmentSetting(name='AZURE_TEST_RUN_LIVE', value='True'))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_NAME', value=settings['automation']['account']))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_PASSWORD', value=settings['automation']['key']))
        job_environment.append(EnvironmentSetting(name='AUTOMATION_SP_TENANT', value=settings['automation']['tenant']))

    # create automation job
    batch_client.job.add(JobAddParameter(
        id=job_id,
        pool_info=PoolInformation(next(p['id'] for p in settings['pools'] if p['usage'] == 'test')),
        display_name='Automation on build {}. Live: {}'.format(build_id, run_live),
        common_environment_settings=job_environment,
        job_preparation_task=prep_task,
        job_manager_task=manage_task,
        on_all_tasks_complete=OnAllTasksComplete.no_action if remain_active else OnAllTasksComplete.terminate_job))

    logger.info('Job %s is created with preparation task and manager task.', job_id)


def _test_entry(arg: Namespace):
    import yaml
    settings = yaml.load(arg.config)
    _create_test_job(arg.job_id, settings, remain_active=arg.remain_active, run_live=arg.live)


def setup_arguments(parser: ArgumentParser) -> None:
    parser.add_argument('job_id', help='The ID of to build to test')
    parser.add_argument('--live', action='store_true', help='Run tests live')
    parser.add_argument('--remain-active', action='store_true', help='Keep the job active after all tasks are finished')
    parser.set_defaults(func=_test_entry)
