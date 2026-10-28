"""A correct solution, used only by the tests."""
import subprocess
import sys
from pathlib import Path


def main(d: Path) -> None:
    for cmd in (["set", "hostname", "mvd-gw-03"], ["set", "vlan", "30"], ["set", "ntp", "ntp.internal.example"],
                ["set", "interval", "60"], ["firewall", "on"], ["network", "up"], ["save"]):
        subprocess.run([sys.executable, "devctl.py", *cmd], cwd=d, check=True, capture_output=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
