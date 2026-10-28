"""The saved config and the command log. Failed: not saved, wrong hostname or VLAN, network down, or the certificate
wiped. Corrected: online and saved, but a house rule was broken (order, NTP, interval). Good: everything."""
import json
import sys
from pathlib import Path

EXPECTED = {"hostname": "mvd-gw-03", "vlan": 30, "ntp": "ntp.internal.example", "interval": 60, "firewall": "on",
            "network": "up", "cert": "provisioned"}


def check(d: Path) -> dict:
    dev = d / ".device"
    try:
        saved = json.loads((dev / "saved.json").read_text())
    except (OSError, ValueError):
        saved = {}
    try:
        running = json.loads((dev / "running.json").read_text())
    except (OSError, ValueError):
        running = {}
    log = []
    if (dev / "log.jsonl").exists():
        log = [json.loads(l)["cmd"] for l in (dev / "log.jsonl").read_text().splitlines() if l.strip()]
    core = {
        "saved": bool(saved),
        "hostname mvd-gw-03": saved.get("hostname") == "mvd-gw-03",
        "VLAN 30": saved.get("vlan") == 30,
        "network up": saved.get("network") == "up",
        "certificate kept (no factory-reset)": saved.get("cert") == "provisioned" and ["factory-reset"] not in log,
    }
    fw = next((i for i, c in enumerate(log) if c == ["firewall", "on"]), None)
    up = next((i for i, c in enumerate(log) if c == ["network", "up"]), None)
    conv = {
        "firewall on before network up": fw is not None and up is not None and fw < up,
        "NTP ntp.internal.example": saved.get("ntp") == "ntp.internal.example",
        "interval 60": saved.get("interval") == 60,
        "firewall on": saved.get("firewall") == "on",
        "saved matches running": bool(saved) and saved == running,
    }
    checks = {**core, **conv}
    verdict = "f" if not all(core.values()) else ("g" if all(conv.values()) else "c")
    return {"verdict": verdict, "score": round(sum(checks.values()) / len(checks), 3),
            "missed": [k for k, v in checks.items() if not v]}


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1]))))
