#!/usr/bin/env python3
"""
Kaffero print agent: prints kitchen tickets on the restaurant's Wi-Fi printers.

Run it on any always-on computer at the outlet that is on the same Wi-Fi as the
printers (a PC at the counter, a Raspberry Pi, a spare laptop). It needs only
Python 3.8+ and no extra packages.

    python3 kaffero_print_agent.py --server https://kaffero.app --token YOUR_TOKEN

The token comes from Dashboard > Kitchen Stations > Print agent. The server can
also be given as KAFFERO_SERVER and the token as KAFFERO_TOKEN.

Every couple of seconds the agent asks the server for queued tickets, sends each
one to its printer (raw ESC/POS on port 9100) and reports back. If a printer is
off or out of paper the ticket is retried automatically.
"""

import argparse
import base64
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0"
POLL_SECONDS = 2.0
PRINTER_TIMEOUT = 8.0
HTTP_TIMEOUT = 15.0

log = logging.getLogger("kaffero-print-agent")


class Agent:
    def __init__(self, server, token):
        self.server = server.rstrip("/")
        self.token = token

    def _post(self, path, body=None):
        data = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            self.server + path,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
                "User-Agent": f"KafferoPrintAgent/{VERSION}",
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def poll(self):
        return self._post("/printing/agent/poll/").get("jobs", [])

    def report(self, job_id, ok, error=""):
        try:
            self._post(f"/printing/agent/jobs/{job_id}/report/", {"ok": ok, "error": error})
        except Exception as exc:  # the server requeues unreported jobs after a timeout
            log.warning("Could not report job %s: %s", job_id, exc)


def send_to_printer(ip, port, data, copies=1):
    with socket.create_connection((ip, int(port)), timeout=PRINTER_TIMEOUT) as sock:
        sock.settimeout(PRINTER_TIMEOUT)
        for _ in range(max(1, int(copies))):
            sock.sendall(data)


def run(agent):
    log.info("Kaffero print agent %s connected to %s", VERSION, agent.server)
    backoff = POLL_SECONDS
    while True:
        try:
            jobs = agent.poll()
            backoff = POLL_SECONDS
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                log.error("The server rejected the token. Check it in Dashboard > Kitchen Stations.")
                return 2
            log.warning("Server error %s; retrying", exc.code)
            jobs, backoff = [], min(backoff * 2, 30)
        except Exception as exc:
            log.warning("Cannot reach the server (%s); retrying", exc)
            jobs, backoff = [], min(backoff * 2, 30)

        for job in jobs:
            title = job.get("title") or f"job {job['id']}"
            try:
                send_to_printer(job["printer_ip"], job["printer_port"], base64.b64decode(job["payload"]), job.get("copies", 1))
                log.info("Printed %s on %s", title, job["printer_ip"])
                agent.report(job["id"], True)
            except Exception as exc:
                log.warning("Printer %s failed for %s: %s", job["printer_ip"], title, exc)
                agent.report(job["id"], False, f"{type(exc).__name__}: {exc}")

        time.sleep(backoff)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print Kaffero kitchen tickets on Wi-Fi printers.")
    parser.add_argument("--server", default=os.environ.get("KAFFERO_SERVER", ""), help="e.g. https://kaffero.app")
    parser.add_argument("--token", default=os.environ.get("KAFFERO_TOKEN", ""), help="print agent token")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not args.server or not args.token:
        parser.error("--server and --token are required (or set KAFFERO_SERVER and KAFFERO_TOKEN)")
    try:
        return run(Agent(args.server, args.token))
    except KeyboardInterrupt:
        log.info("Stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
