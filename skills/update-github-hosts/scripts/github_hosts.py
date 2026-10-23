#!/usr/bin/env python3
"""Discover, probe, and stage safe updates to GitHub entries in /etc/hosts."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


CURL = "/usr/bin/curl"
DIG = "/usr/bin/dig"
META_URL = "https://api.github.com/meta"
GITHUB520_URL = "https://raw.hellogithub.com/hosts"


def validate_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid IP address: {value}") from exc


def probe_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", default="github.com")
    parser.add_argument(
        "--path",
        default="/",
        help="HTTPS path used for probing, for example /robots.txt.",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--connect-timeout", type=float, default=4.0)
    parser.add_argument("--request-timeout", type=float, default=8.0)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--finalists", type=int, default=8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover GitHub IPs, probe candidates, or stage a hosts update."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser(
        "discover", help="Discover candidates from live sources and probe them."
    )
    probe_options(discover)
    discover.add_argument(
        "--category",
        default="web",
        help="GitHub Meta API category, e.g. web, api, or git.",
    )
    discover.add_argument("--hosts-source", default="/etc/hosts")
    discover.add_argument("--no-meta", action="store_true")
    discover.add_argument("--no-dns", action="store_true")
    discover.add_argument("--no-hosts", action="store_true")
    discover.add_argument("--no-github520", action="store_true")

    probe = subparsers.add_parser(
        "probe", help="Measure explicitly supplied candidate IPs."
    )
    probe_options(probe)
    probe.add_argument("--candidates", nargs="+", required=True, type=validate_ip)

    stage = subparsers.add_parser(
        "stage", help="Replace exactly one active mapping in a hosts file."
    )
    stage.add_argument("--domain", default="github.com")
    stage.add_argument("--ip", required=True, type=validate_ip)
    stage.add_argument("--source", default="/etc/hosts")
    stage.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command in {"discover", "probe"}:
        if args.attempts < 1:
            parser.error("--attempts must be at least 1")
        if args.connect_timeout <= 0 or args.request_timeout <= 0:
            parser.error("timeouts must be positive")
        if args.workers < 1:
            parser.error("--workers must be at least 1")
        if args.finalists < 1:
            parser.error("--finalists must be at least 1")
        if not args.path.startswith("/"):
            parser.error("--path must start with /")
    return args


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def fetch_text(url: str) -> str:
    completed = run_command(
        [
            CURL,
            "-fsSL",
            "--connect-timeout",
            "5",
            "--max-time",
            "20",
            url,
        ]
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip().splitlines()
        raise RuntimeError(reason[-1] if reason else f"failed to fetch {url}")
    return completed.stdout


def add_candidate(
    candidates: dict[str, set[str]],
    value: str,
    source: str,
) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return
    if address.version != 4:
        return
    candidates.setdefault(str(address), set()).add(source)


def parse_hosts_text(text: str, domain: str, source: str) -> dict[str, set[str]]:
    candidates: dict[str, set[str]] = {}
    for line in text.splitlines():
        fields = line.split("#", 1)[0].strip().split()
        if len(fields) < 2 or domain not in fields[1:]:
            continue
        add_candidate(candidates, fields[0], source)
    return candidates


def merge_candidates(
    target: dict[str, set[str]],
    incoming: dict[str, set[str]],
) -> None:
    for ip, sources in incoming.items():
        target.setdefault(ip, set()).update(sources)


def discover_meta(category: str) -> dict[str, set[str]]:
    data = json.loads(fetch_text(META_URL))
    entries = data.get(category)
    if not isinstance(entries, list):
        raise RuntimeError(f"GitHub Meta API has no category {category!r}")

    candidates: dict[str, set[str]] = {}
    for entry in entries:
        try:
            network = ipaddress.ip_network(str(entry), strict=False)
        except ValueError:
            continue
        if network.version == 4 and network.prefixlen == 32:
            add_candidate(candidates, str(network.network_address), f"meta/{category}")
    return candidates


def discover_dns(domain: str) -> dict[str, set[str]]:
    completed = run_command(
        [DIG, "+short", "+time=2", "+tries=1", "A", domain]
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip().splitlines()
        raise RuntimeError(reason[-1] if reason else "dig failed")

    candidates: dict[str, set[str]] = {}
    for line in completed.stdout.splitlines():
        add_candidate(candidates, line.strip(), "dns")
    return candidates


def discover_hosts(path: str, domain: str) -> dict[str, set[str]]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    return parse_hosts_text(text, domain, "hosts")


def discover_github520(domain: str) -> dict[str, set[str]]:
    return parse_hosts_text(fetch_text(GITHUB520_URL), domain, "github520")


def collect_candidates(
    args: argparse.Namespace,
) -> tuple[dict[str, set[str]], list[str]]:
    candidates: dict[str, set[str]] = {}
    warnings: list[str] = []

    sources = []
    if not args.no_meta:
        sources.append(
            (
                f"meta/{args.category}",
                lambda: discover_meta(args.category),
            )
        )
    if not args.no_dns:
        sources.append((f"dns/{args.domain}", lambda: discover_dns(args.domain)))
    if not args.no_hosts:
        sources.append(
            (
                f"hosts:{args.hosts_source}",
                lambda: discover_hosts(args.hosts_source, args.domain),
            )
        )
    if not args.no_github520:
        sources.append(("github520", lambda: discover_github520(args.domain)))

    for label, discover in sources:
        try:
            incoming = discover()
        except Exception as exc:
            warnings.append(f"{label}: {exc}")
            continue
        merge_candidates(candidates, incoming)
        print(f"Source {label}: {len(incoming)} candidate(s)")

    return candidates, warnings


def run_probe(
    domain: str,
    path: str,
    ip: str,
    connect_timeout: float,
    request_timeout: float,
) -> tuple[bool, float | None, float | None, str]:
    completed = run_command(
        [
            CURL,
            "-IsS",
            "--connect-timeout",
            str(connect_timeout),
            "--max-time",
            str(request_timeout),
            "--resolve",
            f"{domain}:443:{ip}",
            f"https://{domain}{path}",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code} %{time_connect} %{time_total}",
        ]
    )
    output = completed.stdout.strip().split()
    if completed.returncode != 0 or len(output) != 3:
        reason = completed.stderr.strip().splitlines()
        return False, None, None, reason[-1] if reason else "curl failed"

    try:
        status = int(output[0])
        connect_time = float(output[1])
        total_time = float(output[2])
    except ValueError:
        return False, None, None, f"unexpected curl output: {completed.stdout!r}"

    if 200 <= status < 400:
        return True, connect_time, total_time, str(status)
    return False, connect_time, total_time, f"HTTP {status}"


def run_probe_round(
    ips: list[str],
    args: argparse.Namespace,
) -> dict[str, tuple[bool, float | None, float | None, str]]:
    results: dict[str, tuple[bool, float | None, float | None, str]] = {}
    with ThreadPoolExecutor(max_workers=min(args.workers, len(ips))) as executor:
        futures = {
            executor.submit(
                run_probe,
                args.domain,
                args.path,
                ip,
                args.connect_timeout,
                args.request_timeout,
            ): ip
            for ip in ips
        }
        for future in as_completed(futures):
            ip = futures[future]
            try:
                results[ip] = future.result()
            except Exception as exc:
                results[ip] = (False, None, None, str(exc))
    return results


def probe_candidates(
    candidates: dict[str, set[str]],
    args: argparse.Namespace,
) -> int:
    if not candidates:
        print("No candidates discovered.", file=sys.stderr)
        return 1

    ips = sorted(candidates)
    print(f"Probing {len(ips)} unique candidate(s) against https://{args.domain}{args.path}")
    attempts: dict[str, list[tuple[bool, float | None, float | None, str]]] = {
        ip: [] for ip in ips
    }

    initial = run_probe_round(ips, args)
    for ip, result in initial.items():
        attempts[ip].append(result)

    successful = sorted(
        (ip for ip in ips if initial[ip][0]),
        key=lambda ip: initial[ip][2] or float("inf"),
    )
    finalists = successful[: args.finalists]
    if args.attempts > 1 and finalists:
        for _ in range(args.attempts - 1):
            round_results = run_probe_round(finalists, args)
            for ip, result in round_results.items():
                attempts[ip].append(result)

    ranked = []
    for ip in ips:
        results = attempts[ip]
        successes = sum(1 for result in results if result[0])
        total_times = [
            result[2]
            for result in results
            if result[0] and result[2] is not None
        ]
        connect_times = [
            result[1]
            for result in results
            if result[0] and result[1] is not None
        ]
        median_total = statistics.median(total_times) if total_times else float("inf")
        median_connect = (
            statistics.median(connect_times) if connect_times else float("inf")
        )
        ranked.append(
            (
                successes,
                median_connect,
                median_total,
                ip,
                results,
                candidates[ip],
            )
        )

    ranked.sort(key=lambda item: (-item[0], item[2], item[1]))
    print("IP                 OK   Connect(med)  Total(med)  Sources")
    for successes, connect_time, total_time, ip, results, sources in ranked:
        connect_text = f"{connect_time:.3f}s" if connect_time != float("inf") else "-"
        total_text = f"{total_time:.3f}s" if total_time != float("inf") else "-"
        print(
            f"{ip:<18} {successes}/{len(results)}  "
            f"{connect_text:<12}  {total_text:<10}  "
            f"{', '.join(sorted(sources))}"
        )

    winner = ranked[0]
    if winner[0] == 0:
        print("No candidate passed HTTPS probing.", file=sys.stderr)
        return 1

    print(f"Recommended: {winner[3]}")
    if winner[0] < len(winner[4]):
        print(
            "Warning: the recommended route was intermittent; probe again before applying.",
            file=sys.stderr,
        )
    return 0


def discover(args: argparse.Namespace) -> int:
    candidates, warnings = collect_candidates(args)
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return probe_candidates(candidates, args)


def probe(args: argparse.Namespace) -> int:
    candidates = {ip: {"manual"} for ip in args.candidates}
    return probe_candidates(candidates, args)


def stage(args: argparse.Namespace) -> int:
    source = Path(args.source)
    output = Path(args.output)
    if source.resolve() == output.resolve():
        print("Refusing to overwrite the source hosts file.", file=sys.stderr)
        return 2

    try:
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        print(f"Cannot read {source}: {exc}", file=sys.stderr)
        return 2

    matches: list[int] = []
    for index, line in enumerate(lines):
        active = line.split("#", 1)[0].strip()
        fields = active.split()
        if len(fields) >= 2 and args.domain in fields[1:]:
            matches.append(index)

    if not matches:
        print(
            f"No active mapping found for {args.domain}; refusing to guess.",
            file=sys.stderr,
        )
        return 2
    if len(matches) > 1:
        locations = ", ".join(str(index + 1) for index in matches)
        print(
            f"Multiple active mappings found for {args.domain} at lines "
            f"{locations}; merge duplicate blocks first.",
            file=sys.stderr,
        )
        return 2

    index = matches[0]
    old_line = lines[index]
    body = old_line.rstrip("\r\n")
    ending = old_line[len(body):]
    match = re.match(r"^(\s*)\S+(\s+)(.*)$", body)
    if not match:
        print(f"Cannot parse line {index + 1}: {old_line!r}", file=sys.stderr)
        return 2

    new_line = (
        f"{match.group(1)}{args.ip}{match.group(2)}{match.group(3)}{ending}"
    )
    if new_line == old_line:
        print(f"{args.domain} already maps to {args.ip}.")
        return 0

    lines[index] = new_line
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as temp_file:
        temp_file.writelines(lines)
        temp_path = Path(temp_file.name)
    temp_path.replace(output)

    print(f"Staged line {index + 1}:")
    print(f"- {old_line.rstrip()}")
    print(f"+ {new_line.rstrip()}")
    print(f"Output: {output}")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "discover":
        return discover(args)
    if args.command == "probe":
        return probe(args)
    return stage(args)


if __name__ == "__main__":
    raise SystemExit(main())
