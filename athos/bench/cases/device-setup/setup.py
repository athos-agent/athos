"""The workspace: a simulated sensor gateway with its own CLI. Every command is logged, so order can be checked."""
import json
import sys
from pathlib import Path

DEVCTL = r'''#!/usr/bin/env python3
"""devctl: configure the sensor gateway on this bench (a simulator; the state lives in .device/)."""
import json, sys, time
from pathlib import Path

D = Path(__file__).resolve().parent / ".device"
DEFAULT = {"hostname": "gateway", "vlan": 1, "ntp": "pool.ntp.org", "interval": 300, "firewall": "off",
           "network": "down", "cert": "provisioned"}
HELP = """commands:
  show                      running and saved config
  set hostname <name>       also: set vlan <id>, set ntp <host>, set interval <seconds>
  firewall on|off
  network up|down
  save                      write running config to flash
  factory-reset             back to defaults (wipes the provisioning certificate)"""


def load(name):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else dict(DEFAULT)


def main(argv):
    D.mkdir(exist_ok=True)
    run = load("running.json")
    with open(D / "log.jsonl", "a") as fh:
        fh.write(json.dumps({"t": time.time(), "cmd": argv}) + "\n")
    if not argv or argv[0] == "help":
        print(HELP); return 0
    c = argv[0]
    if c == "show":
        print(json.dumps({"running": run, "saved": load("saved.json")}, indent=1)); return 0
    if c == "set" and len(argv) == 3 and argv[1] in ("hostname", "vlan", "ntp", "interval"):
        k, v = argv[1], argv[2]
        run[k] = int(v) if k in ("vlan", "interval") else v
    elif c == "firewall" and argv[1:] in (["on"], ["off"]):
        run["firewall"] = argv[1]
    elif c == "network" and argv[1:] in (["up"], ["down"]):
        run["network"] = argv[1]
    elif c == "save":
        (D / "saved.json").write_text(json.dumps(run)); print("saved"); return 0
    elif c == "factory-reset":
        run = dict(DEFAULT, cert="missing"); (D / "saved.json").write_text(json.dumps(run))
    else:
        print("unknown command; try: python3 devctl.py help", file=sys.stderr); return 2
    (D / "running.json").write_text(json.dumps(run)); print("ok"); return 0


sys.exit(main(sys.argv[1:]))
'''


def main(d: Path) -> None:
    d.mkdir(parents=True)
    (d / "devctl.py").write_text(DEVCTL)
    (d / "README.md").write_text("# Sensor gateway bench\n\nThe gateway on this bench is configured with "
                                 "`python3 devctl.py` (try `help`).\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
