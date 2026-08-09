#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/var/www/camp-status")
KUBECTL = "/usr/local/bin/kubectl"
WATCH_LINE = re.compile(
    r"\[(?P<id>[a-z0-9-]+)] available=(?P<available>True|False);"
    r"(?P<detail>.*?); url=(?P<url>\S+)"
)


def run(*args):
    try:
        result = subprocess.run(
            [KUBECTL, *args], text=True, capture_output=True,
            timeout=15, check=True,
        )
        return result.stdout.strip(), ""
    except Exception as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        return "", detail.strip()


def atomic_write(path, content):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def memory_percent():
    values = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        return round((values["MemTotal"] - values["MemAvailable"]) * 100 / values["MemTotal"])
    except Exception:
        return None


def configured_watches(config):
    watches = config.get("watches")
    if isinstance(watches, list) and watches:
        return watches
    if config.get("campground"):
        return [{
            "id": "legacy-watch",
            "campground": config.get("campground"),
            "arrival": config.get("arrival"),
            "nights": config.get("nights"),
        }]
    return []


def parse_watch_results(logs, watches):
    results = {
        watch["id"]: {
            "id": watch["id"],
            "campground": watch.get("campground", "Unknown campground"),
            "arrival": watch.get("arrival"),
            "nights": watch.get("nights"),
            "available": None,
            "available_count": None,
            "last_check": None,
            "booking_url": None,
        }
        for watch in watches
    }
    lines = [line for line in logs.splitlines() if line.strip()]
    for line in reversed(lines):
        match = WATCH_LINE.search(line)
        if not match or match.group("id") not in results:
            continue
        item = results[match.group("id")]
        if item["last_check"] is not None:
            continue
        count_match = re.search(r"matching sites available=(\d+)", match.group("detail"))
        item.update({
            "available": match.group("available") == "True",
            "available_count": int(count_match.group(1)) if count_match else None,
            "last_check": line,
            "booking_url": match.group("url"),
        })

    # One-release compatibility for logs produced by the old single-watch monitor.
    if watches and results[watches[0]["id"]]["last_check"] is None:
        for line in reversed(lines):
            if "available=" not in line and "matching sites available=" not in line:
                continue
            count_match = re.search(r"matching sites available=(\d+)", line)
            count = int(count_match.group(1)) if count_match else None
            results[watches[0]["id"]].update({
                "available": "available=True" in line or (count is not None and count > 0),
                "available_count": count,
                "last_check": line,
            })
            break
    return list(results.values())


def collect():
    errors = []
    pod_raw, err = run("-n", "camp-monitor", "get", "pods", "-l", "app.kubernetes.io/name=camp-monitor", "-o", "json")
    if err:
        errors.append(err)
    app_raw, err = run("-n", "argocd", "get", "application", "camp-monitor", "-o", "json")
    if err:
        errors.append(err)
    config_raw, err = run("-n", "camp-monitor", "get", "configmap", "-o", "json")
    if err:
        errors.append(err)
    logs, err = run("-n", "camp-monitor", "logs", "deployment/camp-monitor", "--tail=250", "--timestamps=true")
    if err:
        errors.append(err)

    items = json.loads(pod_raw).get("items", []) if pod_raw else []
    pod = items[0] if items else {}
    app = json.loads(app_raw) if app_raw else {}
    config = {}
    if config_raw:
        for item in json.loads(config_raw).get("items", []):
            if item.get("metadata", {}).get("name", "").startswith("camp-monitor-config-"):
                config = json.loads(item.get("data", {}).get("config.json", "{}"))
                break

    conditions = pod.get("status", {}).get("conditions", [])
    ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
    containers = pod.get("status", {}).get("containerStatuses", [])
    app_status = app.get("status", {})
    argo_sync = app_status.get("sync", {}).get("status", "Unknown")
    argo_health = app_status.get("health", {}).get("status", "Unknown")
    watches = parse_watch_results(logs, configured_watches(config))
    reporting = sum(watch["available"] is not None for watch in watches)
    available_watches = sum(watch["available"] is True for watch in watches)
    disk = shutil.disk_usage("/")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": "Normal" if ready and argo_sync == "Synced" and argo_health == "Healthy" else "Check system",
        "pod_phase": pod.get("status", {}).get("phase", "Unknown"),
        "pod_ready": ready,
        "restarts": sum(c.get("restartCount", 0) for c in containers),
        "argo_sync": argo_sync,
        "argo_health": argo_health,
        "revision": app_status.get("sync", {}).get("revision", "")[:7],
        "interval_minutes": round(config.get("check_interval_seconds", 0) / 60) if config.get("check_interval_seconds") else None,
        "watch_count": len(watches),
        "reporting_count": reporting,
        "available_watch_count": available_watches,
        "watches": watches,
        "memory_percent": memory_percent(),
        "disk_percent": round(disk.used * 100 / disk.total),
        "error": " | ".join(dict.fromkeys(errors)),
    }
    atomic_write(OUT / "status.json", json.dumps(payload, ensure_ascii=False))
    atomic_write(OUT / "logs.txt", logs + ("\n" if logs else ""))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            collect()
        except Exception as exc:
            atomic_write(OUT / "status.json", json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overall": "Collector error",
                "watches": [],
                "error": str(exc),
            }, ensure_ascii=False))
        time.sleep(5)


if __name__ == "__main__":
    main()
