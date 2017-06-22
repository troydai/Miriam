#!/usr/bin/env python3

import json
import datetime

from azure.batch.models import TaskAddParameter, JobAddParameter, PoolInformation
from azure.batch import BatchServiceClient
from azure.batch.batch_auth import SharedKeyCredentials


def get_command_string(*args):
    """Generate a bash facing one-line command."""
    return "/bin/bash -c 'set -e; set -o pipefail; {}; wait'".format(';'.join(args))


def main():
    # read the settings
    with open('config.json', 'r') as fq:
        settings = json.load(fq)

    # 1. schedule a job to build project and test packages
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    bc = BatchServiceClient(cred, settings['azurebatch']['endpoint'])
    pool = bc.pool.get(settings['azurebatch']['pool'])

    print('found pool', pool.id)

    job_id = 'job-{}'.format(datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S'))
    bc.job.add(JobAddParameter(job_id, PoolInformation(pool.id), uses_task_dependencies=True))
    job = bc.job.get(job_id)

    print('create job', job.id)

    build_cmds = [
        'git clone -b {} -- {} gitsrc'.format(settings['gitsource']['branch'], settings['gitsource']['url']),
        'cd gitsrc',
        './scripts/batch/build_all.sh',
        'ls -R ./artifacts/build'
    ]
    build_task = TaskAddParameter(id='build',
                                  command_line=get_command_string(*build_cmds),
                                  display_name='Build all product and test code.')
    bc.task.add(job.id, build_task)

    print('create build task')


if __name__ == '__main__':
    main()