#!/usr/bin/env python3
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta

from azure.batch import BatchServiceClient
from azure.batch.models import CloudTask
from azure.storage.blob import BlockBlobService


def create_batch_client(settings: dict) -> BatchServiceClient:
    from azure.batch.batch_auth import SharedKeyCredentials
    cred = SharedKeyCredentials(
        settings['azurebatch']['account'], settings['azurebatch']['key'])
    return BatchServiceClient(cred, settings['azurebatch']['endpoint'])


def create_storage_client(settings):
    return BlockBlobService(settings['azurestorage']['account'], settings['azurestorage']['key'])


def get_log_blob_url(run_id: str, settings: dict, include_log: bool):
    if not include_log:
        return None

    storage = create_storage_client(settings)

    def _func(task: CloudTask):
        import os.path
        from azure.storage.blob.models import BlobPermissions

        blob_name = os.path.join(task.id, 'stdout.txt')
        container_name = f'output-{run_id}'
        sas = storage.generate_blob_shared_access_signature(container_name, blob_name,
                                                            permission=BlobPermissions(read=True),
                                                            protocol='https',
                                                            expiry=(datetime.utcnow() + timedelta(weeks=52)))
        return storage.make_blob_url(container_name, blob_name, sas_token=sas, protocol='https')

    return _func


def query_results(settings: dict, run_id: str, failed_only: bool = False):
    batch = create_batch_client(settings)
    for t in batch.task.list(run_id):  # TODO: try use OData filter. But I hate OData!
        if t.execution_info.exit_code == 0 and failed_only:
            continue
        if t.id == 'test-creator':
            continue
        yield t


def parse_tests(results_query, log_blob_url_fn, html: bool):
    for index, t in enumerate(results_query):
        row = [index + 1]

        _, test_method, test_class = t.display_name.split(' ')
        test_class = test_class.strip('()')

        parts = test_class.split('.')
        class_name = parts[-1]
        if test_class.startswith('azure.cli.command_modules.'):
            row.append(parts[3].upper())
        elif test_class.startswith('azure.cli.'):
            row.append(parts[2].upper())
        else:
            raise ValueError('Unexpected test display name: {}'.format(t.display_name))

        row.append(f'{test_method} ({class_name})')
        row.append(t.execution_info.exit_code)
        row.append((t.execution_info.end_time - t.execution_info.start_time).total_seconds())

        if log_blob_url_fn:
            url = log_blob_url_fn(t)
            row.append(f'<a href="{url}">Log</a>' if html else url)

        yield row


def main(run_id: str, failed_only: bool, include_log: bool, html: bool):
    settings = get_settings()

    import tabulate

    results_query = query_results(settings, run_id, failed_only)
    results = parse_tests(results_query, get_log_blob_url(run_id, settings, include_log), html)

    headers = ['Module', 'Test (Class)', 'Exit Code', 'Duration']
    if include_log:
        headers.append('Output Blob URL')

    output = tabulate.tabulate(results, headers=headers, tablefmt='html' if html else 'simple')
    if html:
        with open('results.html', 'w') as fq:
            fq.write(build_html_page(run_id, output))
        print('Output is written to results.html')
    else:
        print(output)


def build_html_page(run_id: str, table_output: str):
    return """
<html>
<head>
<title>Test results {0}</title>
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
</head>
<div class='container'>
<div class='row'>
<h1>Azure CLI Automation Result</h1>
<dl class="dl-horizontal">
  <dt>Run ID</dt>
  <dd>{0}</dd>
</dl>
</div>
<div class='row'>
<body>
{1}
</body>
</div>
</div>
</html>
""".format(run_id, table_output).replace('<table>', '<table class="table table-condensed table-striped">')


def get_settings():
    try:
        import yaml
        import os.path

        with open(os.path.expanduser('~/.miriam/config.yaml'), 'r') as fq:
            return yaml.load(fq)
    except (IOError, KeyError):
        sys.stderr.write('Fail to load config (~/.miriam/config.yaml).\n')
        sys.exit(1)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('run_id', help='The test run id from which the results are collected.')
    parser.add_argument('--failed', action='store_true', help='List the failed tests only.')
    parser.add_argument('--include-log', action='store_true', help='List the url to the log blob.')
    parser.add_argument('--html', action='store_true', help='Output the result in a readable list.')
    args = parser.parse_args()

    main(args.run_id, args.failed, args.include_log, args.html)
