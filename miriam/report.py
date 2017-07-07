import argparse
from azure.batch.models import CloudTask


def _get_task_log(run_id: str, task: CloudTask, settings: dict) -> str:
    import os.path
    import requests
    from datetime import datetime, timedelta

    from azure.storage.blob.models import BlobPermissions
    from miriam._utility import create_storage_client

    storage = create_storage_client(settings)

    blob_name = os.path.join(task.id, 'stdout.txt')
    container_name = f'output-{run_id}'
    sas = storage.generate_blob_shared_access_signature(container_name, blob_name,
                                                        permission=BlobPermissions(read=True),
                                                        protocol='https',
                                                        expiry=(datetime.utcnow() + timedelta(weeks=52)))
    url = storage.make_blob_url(container_name, blob_name, sas_token=sas, protocol='https')

    response = requests.request('GET', url)
    return '\n'.join(response.text.split('\n')[58:-3])


def _query_results(settings: dict, run_id: str, failed_only: bool = False):
    from miriam._utility import create_batch_client

    batch = create_batch_client(settings)
    for task in batch.task.list(run_id):  # try use OData filter. But I hate OData!
        if task.execution_info.exit_code == 0 and failed_only:
            continue
        if task.id == 'test-creator':
            continue
        yield task


def _parse_tests(task_lists: list):
    for index, task in enumerate(task_lists):
        row = [index + 1]

        _, test_method, test_class = task.display_name.split(' ')
        test_class = test_class.strip('()')

        parts = test_class.split('.')
        class_name = parts[-1]
        if test_class.startswith('azure.cli.command_modules.'):
            row.append(parts[3].upper())
        elif test_class.startswith('azure.cli.'):
            row.append(parts[2].upper())
        else:
            raise ValueError('Unexpected test display name: {}'.format(task.display_name))

        row.append(f'{test_method} ({class_name})')
        row.append(task.execution_info.exit_code)
        row.append((task.execution_info.end_time - task.execution_info.start_time).total_seconds())

        yield row


def _report(args: argparse.Namespace) -> None:
    import yaml
    settings = yaml.load(args.config)

    tasks_list = list(_query_results(settings, args.run_id, args.failed_only))
    tasks_results = list(_parse_tests(tasks_list))

    if args.include_log and args.html:
        tasks_logs = list(_get_task_log(args.run_id, task, settings) for task in tasks_list)
    else:
        tasks_logs = list()

    headers = ['ID', 'Module', 'Test (Class)', 'Exit Code', 'Duration']

    if args.include_log:
        headers.append('Log')

    if args.html:
        with open('results.html', 'w') as html_file:
            html_file.write(_build_html_page(args.run_id, headers, tasks_results, tasks_logs))
        print('Output is written to results.html')
    else:
        import tabulate
        print(tabulate.tabulate(tasks_results, headers=headers))


def _build_html_page(run_id: str, headers: list, test_results: list, test_logs: list) -> str:
    import tabulate

    results_log = ''
    for idx, test_log in enumerate(test_logs):
        test_name = test_results[idx][2]
        results_log += f'<div class=\'row\'><h4 id={idx}>{test_name}</h4><pre><code>{test_log}</code></pre></div>'

    if results_log:
        for idx, test_result in enumerate(test_results):
            test_result.append(f'<a href="#{idx}">Log</a>')
    results_table = tabulate.tabulate(test_results, headers=headers, tablefmt='html')

    return """
<html>
<head>
<title>Test results {0}</title>
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
</head>
<body>
<div class='container'>
<div class='row'>
<h1>Azure CLI Automation Result</h1>
<dl class="dl-horizontal">
  <dt>Run ID</dt>
  <dd>{0}</dd>
</dl>
</div>
<div class='row'>
{1}
</div>
{2}
</div>
</body>
</html>
""".format(run_id, results_table, results_log).replace('<table>', '<table class="table table-condensed table-striped">')


def setup(subparsers) -> None:
    parser = subparsers.add_parser('report', help='Report the results of a test job.')
    parser.add_argument('run_id', help='The test run id from which the results are collected.')

    parser.add_argument('--html', action='store_true', help='Output the result in an HTML page.')
    parser.add_argument('--failed', action='store_true', help='List the failed tests only.')
    parser.add_argument('--include-log', action='store_true',
                        help='List the url to the log blob. Only works with HTML output')
    parser.set_defaults(func=_report)
