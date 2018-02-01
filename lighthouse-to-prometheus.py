#!/usr/bin/env python3
"""Run lighthouse on one or more sites and POST the results to Prometheus"""

import argparse
import json
import subprocess
import sys

import requests


def run_lighthouse(url, *, chrome_flags=None):
    base_cmd = ['lighthouse', '--perf', '--output=json']

    if chrome_flags:
        base_cmd.append(chrome_flags)

    print(f'Launching lighthouse for {url}…')

    child_result = subprocess.run(base_cmd + [url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if child_result.returncode != 0:
        print(child_result.stderr, file=sys.stderr)
        raise RuntimeError(f'Child process returned {child_result.returncode}')

    return json.loads(child_result.stdout)


def extract_metrics_from_report(data):
    # We'll build list of metric names, Prometheus-style (key, value) label pairs, and a numeric value:
    labels = (('instance', data['url']), )

    results = [
        ('total_time', labels, data['timing']['total']),
        ('total_score', labels, data['score']),
    ]

    for section in data['reportCategories']:
        section_name = section['name']

        results.append(('section_score', labels + (('section', section_name), ), section['score']))

        for audit in section['audits']:
            results.append((
                'audit_score',
                labels + (('section', section_name), ('id', audit['id'])),
                audit['score']
            ))

    return results


def push_results(pushgateway_url, results):
    flat_results = [
        '# TYPE total_time gauge',
        '# TYPE total_score gauge',
        '# TYPE section_score gauge',
        '# TYPE audit_score gauge',
    ]
    for metric_name, labels, value in results:
        flat_labels = '{%s}' % ','.join(f'{key}="{value}"' for key, value in labels)
        flat_results.append(f'{metric_name}{flat_labels} {value}')
    # n.b. Prometheus' text format *requires* a trailing
    response = requests.post(pushgateway_url, "%s\n" % "\n".join(flat_results))

    if not response.ok:
        print(f'Error pushing results to {pushgateway_url}: HTTP {response.status_code} {response.reason}',
              file=sys.stderr)
        print(response.text, file=sys.stderr)
        print(flat_results, file=sys.stderr)
        response.raise_for_status()

    print(f'Pushed {len(results)} results to {pushgateway_url}: {results[0]}…')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument(
        '--chrome-flags', default="",
        help='Optional flags to pass to Chrome: e.g. --chrome-flags="--proxy-server=socks5://localhost:1080"'
    )
    parser.add_argument('--pushgateway', default="http://prometheus:9091/metrics/job/lighthouse")
    parser.add_argument('urls', metavar="URL", nargs="+")
    args = parser.parse_args()

    results = []

    for url in args.urls:
        lighthouse_report = run_lighthouse(url, chrome_flags=args.chrome_flags)

        results.extend(extract_metrics_from_report(lighthouse_report))

    push_results(args.pushgateway, results)
