#!/usr/bin/env python3
import sys

from azure.batch import BatchServiceClient


def create_batch_client(settings: dict) -> BatchServiceClient:
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def parse_failed_tests(job_id: str, bc: BatchServiceClient):
    failed_tasks = (f for f in bc.task.list(job_id) if f.execution_info.exit_code != 0 and f.id != 'test-creator')
    for t in failed_tasks:
        _, test_method, test_class = t.display_name.split(' ')
        test_class = test_class.strip('()')
        if test_class.startswith('azure.cli.command_modules.'):
            parts = test_class.split('.')
            class_name = parts[-1]
            module_name = parts[3]
            yield module_name, class_name, test_method
        else:
            raise ValueError('Unexpected test display name: {}'.format(t.display_name))


def main(job_id: str, settings: dict):
    import tabulate

    bc = create_batch_client(settings)
    failed_tests = parse_failed_tests(job_id, bc)
    print(tabulate.tabulate(failed_tests))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('job_id', help='The job id from which the results are collected.')
    args = parser.parse_args()

    try:
        import json
        import os.path

        with open(os.path.expanduser('~/.miriam/config.json'), 'r') as fq:
            local_settings = json.load(fq)
    except (IOError, KeyError):
        sys.stderr.write('Fail to load config (~/.miriam/config.json).\n')
        sys.exit(1)

    main(args.job_id, local_settings)
