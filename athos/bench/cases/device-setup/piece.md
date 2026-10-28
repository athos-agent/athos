1. Use `python3 devctl.py` in this folder; `python3 devctl.py help` lists the commands and `show` prints the state.
2. Hostname is `<site>-<role>-<nn>`: role `gw` for gateways, `nn` the unit number with two digits (unit 3 → `03`),
   all lowercase. Example: site mvd, gateway unit 3 → `mvd-gw-03`.
3. Sensor gateways go on VLAN 30. NTP server: `ntp.internal.example`. Reporting interval: 60 seconds.
4. Turn the firewall on BEFORE bringing the network up. Never bring a gateway online without its firewall.
5. Never run `factory-reset`: it wipes the provisioning certificate.
6. Finish with `save`: an unsaved config is lost on reboot. Check with `show` that saved and running match.
