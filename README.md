# Network as code

[![CI](https://github.com/rob-in-denver/network-as-code/actions/workflows/network-as-code.yml/badge.svg)](https://github.com/rob-in-denver/network-as-code/actions/workflows/network-as-code.yml)

A small, real example of generating Cisco configuration from a YAML source of truth. It covers three designs:

- a two-site VXLAN BGP EVPN fabric on NX-OS
- a DMVPN Phase 3 hub and spoke on IOS-XE, with IKEv2, a front-door VRF, named EIGRP, and per-spoke route filtering
- an IPv4-only Enterprise Core spanning one `ISP` node (the whole internet), a 6-node MPLS SP Core (`2 × XRv9000` P/RR + `4 × Cat8000v` PE), a Data Center (`DC-R1` CSR1000v DMVPN hub and `DC-R4` on the ISP, `DC-R2`/`DC-R3` MPLS-only, `DC-SW1..DC-SW4` `IOL-L2`), spoke sites with ISP + MPLS transports, and a Cisco SD-WAN 20.12 stack (`SDWAN-MGR`, `SDWAN-VAL`, `SDWAN-CTRL`, vEdge 20.12.8 `DC-CEDGE1/2` and `S1..S3-EDGE`)

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
data/fabric.yml              VXLAN fabric source of truth
data/dmvpn.yml               DMVPN source of truth
data/enterprise_core.yml     ISP + 6-node SP core + DC (4R/4SW) + SD-WAN 20.12 (controllers + vEdges) source of truth
templates/nxos/device.j2     NX-OS Jinja template
templates/iosxe/dmvpn.j2     IOS-XE DMVPN Jinja template
templates/iosxr/sp_p.j2      IOS XR SP P/RR Jinja template
templates/iosxe/sp_pe.j2     Cat8000v SP PE Jinja template
templates/iosxe/dc_router.j2 Data Center router + DC-R1 DMVPN hub Jinja template
templates/iosxe/dc_switch.j2 Data Center distribution/access switch Jinja template
templates/iosxe/isp.j2       Single ISP node (connected routes only) Jinja template
templates/sdwan/vedge.j2     vEdge Cloud 20.12 cloud-init (vinitparam + zcloud.xml) Jinja template
templates/sdwan/controller.j2 SD-WAN Manager/Validator/Controller cloud-init template
playbooks/render.yml         Ansible playbook that renders all designs
rendered/nxos/               Generated NX-OS, committed
rendered/iosxe/              Generated DMVPN IOS-XE, committed
rendered/iosxr/              Generated IOS XR SP Core, committed
rendered/enterprise/         Generated ISP + PE + Data Center IOS-XE/IOL, committed
rendered/sdwan/              Generated SD-WAN vEdge + controller cloud-init, committed
inventory/hosts.yml          Documentation inventory (TEST-NET addresses)
nac/validate.py              Offline checks against the source of truth
nac/collect.py               Optional Netmiko collector, not used by CI
tests/test_nac.py            Unit tests
docs/vxlan-evpn-cml-labs.md  Summary of the related CML VXLAN EVPN lab series
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

## What the Enterprise Core, SP, & SD-WAN data means

`data/enterprise_core.yml` models the IPv4-only shared enterprise backbone used across the CCIE lab series:

| Tier | Nodes | Image / Platform | Routing & Role |
| --- | --- | --- | --- |
| Internet | `ISP` | `iol-xe` | One node is the whole internet: DC-R1 Gi3 `172.16.0.248/30`, DC-R4 Et1/1 `172.16.0.244/30`, VPN0-SW `172.31.0.254/24`, site vEdge biz-internet `/30`s. Connected routes only |
| SP Core | `P1`, `P2` | `iosxrv9000` | OSPF Area 0 + LDP + BGP VPNv4 Route Reflectors (`neighbor-group RR-CLIENTS`, AS 65500) |
| SP Edge | `PE1`–`PE4` | `cat8000v` (`c8000V_Edge_Autonomous`) | OSPF + LDP + MP-BGP VPNv4; VRF `CUST` to branch/DC WAN; `SDWAN-MPLS` (vEdge mpls color, site attachments on `PE1`/`PE2` Gi6–Gi7) and `SDWAN-CTRL` on `PE4` Gi4 `172.31.0.253` so controllers are reachable over MPLS |
| DC DMVPN Hub | `DC-R1` | `csr1000v` (`csr1000V_Edge_Autonomous`) | Phase 3 DMVPN Hub on the ISP (Gi3 `172.16.0.250/30`, `Tunnel10` `10.19.0.1/24`, FVRF `INET`, IKEv2/IPsec, EIGRP AS 210 ↔ OSPF 10) |
| DC WAN & GW | `DC-R2`–`DC-R4` | `iol-xe` | `DC-R2`/`DC-R3` MPLS-only, eBGP AS 65200 ↔ `PE3` VRF `CUST`; `DC-R4` internet edge (Et1/1 to the ISP, static default) + OSPF 10 ↔ `DC-CEDGE1/2` VPN 10 |
| DC Switching | `DC-SW1`–`DC-SW4` | `ioll2-xe` | `DC-SW1`/`DC-SW2` L3 distribution with HSRP (VLANs 10/20/99) + OSPF 10; `DC-SW3`/`DC-SW4` access |
| SD-WAN | `SDWAN-MGR`, `SDWAN-VAL`, `SDWAN-CTRL` | `cat-sdwan-*-20-12-8-1` | SD-WAN 20.12 control plane on `172.31.0.0/24` (`VPN 0`), org `CCIE-LAB`, vBond `172.31.0.20` |
| SD-WAN edges | `DC-CEDGE1/2` (site 200), `S1..S3-EDGE` (sites 301–303) | `cat-sdwan-vedge` (`vedge_20.12.8`) | vEdge Cloud day-0: `biz-internet` (ISP) + `mpls restrict` (SP PE) in VPN 0, VPN 512 mgmt, VPN 10 service LAN. A later move to IOS-XE SD-WAN cEdges needs c8000v 17.12.x |

All configs enforce `ipv4_only: true` and replace secrets/PSK/OTP values with `REDACTED-FROM-VAULT`.

## Related CML labs

The `data/fabric.yml` example above is the compact source of truth in this repository. A larger Cisco Modeling Labs package uses the same VXLAN EVPN multi-site idea as a practice series (two NX-OS fabrics, an MPLS L3VPN provider, and a grader). The four lab variants, including **Lab 4 — Underlay start** (a 4-hour build from a connected IPv4 underlay to intra-fabric and inter-site MP-BGP EVPN), are summarised in [docs/vxlan-evpn-cml-labs.md](docs/vxlan-evpn-cml-labs.md). The CML files and answer keys are not published in this repository.

A companion CCIE-style lab covers Cisco Resilient Ethernet Protocol on two parallel rings of six Catalyst 9000v switches, with an IOL-L2 STP/legacy domain. It is summarised in [docs/rep-dualring-cml-lab.md](docs/rep-dualring-cml-lab.md).

## Secrets

The rendered IOS-XE and SD-WAN configs contain `REDACTED-FROM-VAULT` for PSK, NHRP authentication, and SD-WAN OTP values. That string is not a key. Tests fail if a config contains `password`, `secret`, `cisco123`, or a pre-shared key other than the placeholder.

Put real keys and credentials in Ansible Vault and pass them into the templates at deploy time. Do not commit them.

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
- Add a PE or DC edge node in `data/enterprise_core.yml` and re-run `ansible-playbook playbooks/render.yml`.

## License

[MIT](LICENSE). Copyright 2026 Rob Vrba / ROB IN DENVER LLC.
