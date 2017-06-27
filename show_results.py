#!/usr/bin/env python3
import sys

from azure.batch import BatchServiceClient


def create_batch_client(settings: dict) -> BatchServiceClient:
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def parse_tests(job_id: str, bc: BatchServiceClient, show_failed_only: bool=False):
    for t in bc.task.list(job_id):
        if t.execution_info.exit_code == 0 and show_failed_only:
            continue
        if t.id == 'test-creator':
            continue

        _, test_method, test_class = t.display_name.split(' ')
        test_class = test_class.strip('()')
        parts = test_class.split('.')
        class_name = parts[-1]
        if test_class.startswith('azure.cli.command_modules.'):
            module_name = parts[3]
        elif test_class.startswith('azure.cli.'):
            module_name = parts[2]
        else:
            raise ValueError('Unexpected test display name: {}'.format(t.display_name))

        duration = t.execution_info.end_time - t.execution_info.start_time
        yield module_name, class_name, test_method, t.execution_info.exit_code, duration.total_seconds()


def main(job_id: str, settings: dict, show_failed_only: bool=False):
    import tabulate

    bc = create_batch_client(settings)
    all_tests = parse_tests(job_id, bc, show_failed_only)
    print(tabulate.tabulate(all_tests, headers=('module', 'class', 'test', 'exit', 'duration')))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('job_id', help='The job id from which the results are collected.')
    parser.add_argument('--failed', action='store_true', help='List the failed tests only.')
    args = parser.parse_args()

    try:
        import json
        import os.path

        with open(os.path.expanduser('~/.miriam/config.json'), 'r') as fq:
            local_settings = json.load(fq)
    except (IOError, KeyError):
        sys.stderr.write('Fail to load config (~/.miriam/config.json).\n')
        sys.exit(1)

    main(args.job_id, local_settings, show_failed_only=args.failed)
