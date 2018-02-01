# Save Lighthouse reports to Prometheus

Run one or more sites through [Google's
Lighthouse](https://developers.google.com/web/tools/lighthouse/) and send the
scores to the Prometheus pushgateway:

## Quickstart

```bash
$ pipenv run ./lighthouse-to-prometheus.py --chrome-flags="--proxy-server=socks5://localhost:1080" https://www.loc.gov https://www.wdl.org https://chroniclingamerica.loc.gov https://congress.gov
Launching lighthouse for https://www.loc.gov…
Launching lighthouse for https://www.wdl.org…
Launching lighthouse for https://chroniclingamerica.loc.gov…
Launching lighthouse for https://congress.gov…
Pushed 112 results to http://prometheus:9091/metrics/job/lighthouse: ('total_time', (('instance', 'https://www.loc.gov/'),), 29605)…
```

## Installation

1. `npm install -g lighthouse`
1. `pipenv install`
