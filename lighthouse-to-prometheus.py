#!/usr/bin/env python3
"""Run lighthouse on one or more sites and POST the results to Prometheus"""

import argparse
import json
import subprocess  # nosec
import sys
from urllib.parse import quote

import requests


def run_lighthouse(url, *, chrome_flags=None):
    base_cmd = ["npx", "lighthouse", "--perf", "--output=json"]

    if chrome_flags:
        base_cmd.append("--chrome-flags=%s" % chrome_flags)

    print(f"Launching lighthouse for {url}…")

    child_result = subprocess.run(  # nosec
        base_cmd + [url], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    if child_result.returncode != 0:
        print(child_result.stderr, file=sys.stderr)
        raise RuntimeError(f"Child process returned {child_result.returncode}")

    return json.loads(child_result.stdout)


def extract_metrics_from_report(data):
    # We'll build list of metric names, Prometheus-style (key, value) label
    # pairs, and a numeric value:
    labels = (("instance", data["requestedUrl"]),)

    results = [("lighthouse_scrape_duration_seconds", labels, data["timing"]["total"])]
    # TODO: decide whether we want to have an overall score metric and how to calculate it

    audits = data["audits"]

    for category_id, category in data["categories"].items():
        if category_id in ("seo", "pwa", "accessibility"):
            continue

        results.append(
            (
                "lighthouse_category_score",
                labels + (("category", category_id),),
                category["score"],
            )
        )

        for audit_ref in category["auditRefs"]:
            audit_id = audit_ref["id"]
            audit = audits[audit_id]
            score = audit["score"]

            if score is not None:
                results.append(
                    (
                        "lighthouse_audit_score",
                        labels + (("category", category_id), ("id", audit_id)),
                        score,
                    )
                )

            # We'll pull in a few especially interesting values:
            if audit_id == "first-meaningful-paint":
                results.append(
                    (
                        "lighthouse_first_meaningful_paint_ms",
                        labels,
                        audit["numericValue"],
                    )
                )
            elif audit_id == "speed-index":
                results.append(
                    ("lighthouse_speed_index", labels, audit["numericValue"])
                )

    return results


def push_results(pushgateway_url, results):
    flat_results = [
        "# TYPE lighthouse_scrape_duration_seconds gauge",
        "# TYPE lighthouse_score gauge",
        "# TYPE lighthouse_section_score gauge",
        "# TYPE lighthouse_audit_score gauge",
        "# TYPE lighthouse_speed_index gauge",
        "# TYPE lighthouse_event_ms gauge",
    ]

    for metric_name, labels, value in results:
        flat_labels = "{%s}" % ",".join(f'{key}="{value}"' for key, value in labels)
        flat_results.append(f"{metric_name}{flat_labels} {value}")

    # n.b. Prometheus' text format *requires* a trailing newline:
    response = requests.post(pushgateway_url, "%s\n" % "\n".join(flat_results))

    if not response.ok:
        print(
            f"Error pushing results to {pushgateway_url}:"
            f" HTTP {response.status_code} {response.reason}",
            file=sys.stderr,
        )
        print(response.text, file=sys.stderr)
        print("\n".join(flat_results), file=sys.stderr)
        response.raise_for_status()

    print(f"Pushed {len(results)} results to {pushgateway_url}: {results[0]}…")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument(
        "--chrome-flags",
        default="",
        help='Optional flags to pass to Chrome: e.g. --chrome-flags="--proxy-server=…"',
    )
    parser.add_argument(
        "--pushgateway", default="http://prometheus:9091/metrics/job/lighthouse"
    )
    parser.add_argument(
        "--use-cached-results",
        default=False,
        action="store_true",
        help="Use saved JSON files instead of running tests. Only useful for testing.",
    )
    parser.add_argument("urls", metavar="URL", nargs="+")
    args = parser.parse_args()

    results = []

    for url in args.urls:
        lighthouse_report = None
        cached_result_file = "%s.json" % quote(url, safe="")

        if args.use_cached_results:
            try:
                with open(cached_result_file, "r") as f:
                    lighthouse_report = json.load(f)
            except Exception as exc:
                print(
                    f"Unable to load cached results from {cached_result_file}: {exc}",
                    file=sys.stderr,
                )

        if not lighthouse_report:
            lighthouse_report = run_lighthouse(url, chrome_flags=args.chrome_flags)

        if args.use_cached_results:
            with open(cached_result_file, "w") as f:
                json.dump(lighthouse_report, f)

        results.extend(extract_metrics_from_report(lighthouse_report))

    push_results(args.pushgateway, results)
