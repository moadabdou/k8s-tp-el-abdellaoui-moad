#!/usr/bin/env python3
"""Record each real HTTP probe; keep failed requests in the evidence."""
import csv
import datetime
import sys
import time
import urllib.error
import urllib.request

with open(sys.argv[1], 'w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['utc', 'status', 'hostname', 'latency_ms', 'error'])
    while True:
        started = time.monotonic()
        status, hostname, error = 0, '', ''
        try:
            with urllib.request.urlopen('http://127.0.0.1:30080', timeout=3) as response:
                status = response.status
                body = response.read().decode('utf-8', errors='replace')
                hostname = next((x.partition(':')[2].strip() for x in body.splitlines()
                                 if x.startswith('Hostname:')), '')
        except (OSError, urllib.error.URLError) as exc:
            error = str(exc)
        writer.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         status, hostname, round((time.monotonic()-started)*1000, 2), error])
        stream.flush()
        time.sleep(0.5)
