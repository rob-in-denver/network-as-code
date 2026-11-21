# Network as code

[![CI](https://github.com/rob-in-denver/network-as-code/actions/workflows/network-as-code.yml/badge.svg)](https://github.com/rob-in-denver/network-as-code/actions/workflows/network-as-code.yml)

A small, real example of generating Cisco configuration from a YAML source of truth. It covers two designs:

- a two-site VXLAN BGP EVPN fabric on NX-OS
- a DMVPN Phase 3 hub and spoke on IOS-XE, with IKEv2, a front-door VRF, named EIGRP, and per-spoke route filtering

Ansible and Jinja render the device configs. Pytest checks them. GitHub Actions runs the same steps and does not log into any device.

This repository is part of the [Rob in Denver](https://robindenver.com) portfolio.

## Quickstart

Python 3.12 and a virtualenv. From a clone of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
yamllint .
ansible-playbook playbooks/render.yml
pytest
python -m nac.validate
```

`ansible-playbook` only talks to localhost. `inventory/hosts.yml` documents where a future push would go. It is not used by the render playbook, and it has no credentials.

## Layout

```
data/fabric.yml          VXLAN fabric source of truth
data/dmvpn.yml           DMVPN source of truth
templates/nxos/device.j2 NX-OS Jinja template
templates/iosxe/dmvpn.j2 IOS-XE Jinja template
playbooks/render.yml     Ansible playbook that renders both
rendered/nxos/           Generated NX-OS, committed
rendered/iosxe/          Generated IOS-XE, committed
inventory/hosts.yml      Documentation inventory (TEST-NET addresses)
nac/validate.py          Offline checks against the source of truth
nac/collect.py           Optional Netmiko collector, not used by CI
tests/test_nac.py        Unit tests
```

`rendered/` is a build artifact that is checked in so a reader can see the output without installing Ansible. CI re-renders and fails if the committed files drift.

## What the fabric data means

`data/fabric.yml` describes a fabric named `mesa-multisite`.

| Piece | Value |
| --- | --- |
| Sites | `site-a` ASN 65011, `site-b` ASN 65012 |
| Per site | 2 spines, 2 leaf VTEPs, 2 border gateways |
| Underlay | OSPF process `UNDERLAY`, point-to-point /31 links, MTU 9216 |
| Overlay | iBGP EVPN, spines are route reflectors |
| L2 VNIs | 10010 (VLAN 10) and 10020 (VLAN 20), anycast gateway |
| L3 VNI | 50001 in VRF `APP` |
| Multi-site | BGW anycast VIP per site, eBGP EVPN on the DCI with `rewrite-evpn-rt-asn` |

Every underlay and DCI link is written on both ends. The tests reject a link that is not symmetric, and they reject a reused address. The multi-site VIP is the one address that is intentionally the same on both BGWs in a site.

Changing a VLAN, a VNI, or a link means editing the YAML and re-rendering. The template follows the data.

## What the DMVPN data means

`data/dmvpn.yml` describes one hub (`hub-den1`) and two spokes.

- WAN interfaces are in VRF `WAN` (the front door). Overlay and LAN interfaces are in VRF `CORP`.
- The tunnel is GRE multipoint, sourced from the WAN interface, protected by an IKEv2 profile that matches the front-door VRF.
- Phase 3: the hub has `ip nhrp redirect` and `no next-hop-self` / `no split-horizon`. Spokes have an NHS, `ip nhrp shortcut`, and do not use `ip nhrp map multicast dynamic`.
- Named EIGRP autonomous system 101 runs in VRF `CORP`.
- Each spoke may inject only its own LAN. The hub matches the prefix and the advertising gateway:

```
distribute-list prefix PFX-spoke-north gateway GW-spoke-north in
```

NBMA addresses are documentation ranges (`203.0.113.0/24`, `198.51.100.0/24`, `192.0.2.0/24`).

## Secrets

The rendered IOS-XE contains `pre-shared-key REDACTED-FROM-VAULT` and the same placeholder for NHRP authentication. That string is not a key. Tests fail if a config contains `password`, `secret`, `cisco123`, or a pre-shared key other than the placeholder.

Put a real key in Ansible Vault and pass it into the template at deploy time. Do not commit it.

## CI

[`.github/workflows/network-as-code.yml`](.github/workflows/network-as-code.yml) runs from the repository root on every push and pull request:

1. `yamllint .`
2. `ansible-playbook playbooks/render.yml`
3. `pytest`
4. A diff check so `rendered/` matches what the playbook just wrote

No device, no vault password, and no network login is required.

## Optional live collection

`nac/collect.py` can pull `show running-config` with Netmiko. CI never imports it. To use it yourself:

```bash
pip install netmiko
export NETMIKO_USERNAME=...
export NETMIKO_PASSWORD=...
export NETMIKO_DEVICE_TYPE=cisco_ios   # or cisco_nxos
python -c 'from nac.collect import collect_running_config; print(collect_running_config("192.0.2.1"))'
```

Credentials come from the environment, not from the command line and not from this repo. Point the validator at saved output only after you have decided that output is safe to keep.

## Extending it

- Add a leaf by adding a device, its `/31` links on both ends, and a VTEP loopback. Re-render. The spine template picks up new route-reflector clients on its own.
- Add a VNI in `vnis`. Leaves and border gateways grow the VLAN, the NVE member, and the EVPN stanza.
- Add a spoke in `dmvpn.yml` with a `lan_prefix`. The hub template grows the prefix-lists and the gateway filter.

## License

[MIT](LICENSE). Copyright 2026 Rob Vrba / ROB IN DENVER LLC.
