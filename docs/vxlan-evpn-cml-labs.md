# VXLAN EVPN Multi-Site labs (Cisco Modeling Labs)

This repository's `data/fabric.yml` is a compact, network-as-code example of a two-site VXLAN BGP EVPN fabric (OSPF underlay, iBGP route reflectors, two leaves per site).

A separate, larger **Cisco Modeling Labs** package uses the same ideas at practice-lab scale: two NX-OS 9000v fabrics joined by VXLAN EVPN Multi-Site across an MPLS L3VPN provider. That package lives with the lab files and workbooks; this page is only a public summary. Credentials, planted faults and answer keys are not published here.

## Topology (shared by every variant)

- **DC1** (site-id 100, fabric AS 651xx) and **DC2** (site-id 200, fabric AS 652xx): two IOL-XE spines, four NX-OS leaves (L1/L2 are a vPC pair) and two anycast border gateways per site.
- **Underlay:** eBGP with a distinct ASN per leaf and border gateway; both spines of a site share one ASN.
- **Overlay:** MP-BGP L2VPN EVPN, ingress replication, symmetric IRB, distributed anycast gateway, ARP suppression, dual-stack.
- **Provider (AS 65000):** six IOL-XE routers (PE1–PE4, P1, P2), IS-IS level 2, LDP, VPNv4/VPNv6, P1/P2 as route reflectors. VRF DCI carries border-gateway loopbacks. VRF INET faces a simulated Internet router.
- **Multi-site:** eBGP EVPN, border-gateway loopback to loopback, over the provider's VRF DCI.
- 38 nodes (32 licensed). Running RAM is staged per lab so a start set fits about 96 GB.

## Lab variants

All four labs, and the solved key, describe the same topology. Only the startup configuration changes. The end state of every lab is the solved configuration.

| Lab | Title | Length | Starting point | The candidate builds |
| --- | --- | --- | --- | --- |
| 1 | Fabric build | 6 hours | One site running; underlay and overlay only half done. The provider is already complete. | eBGP underlay, vPC, EVPN overlay, NVE, VNIs, anycast gateway |
| 2 | Multi-site DCI | 6 hours | Both fabrics are done; the provider and the border-gateway DCI pieces are incomplete. | IS-IS/LDP, VRFs, VPNv4/v6, Multi-Site, 6VPE, external hand-off |
| 3 | Troubleshooting | 6 hours | Full topology with ten planted faults and four missing optimisation blocks. | Fix the tickets and apply the optimisations |
| 4 | Underlay start | 4 hours | Fabric switches have hostname, out-of-band addressing, the local user, TCAM carving, loopbacks and IPv4 fabric links only. The provider (IS-IS, LDP, VPNv4, VRF DCI, PE-to-border-gateway addressing) and the Internet router are already complete. | eBGP underlay on both running fabrics, vPC, VLANs/VNIs/IRB/NVE, intra-fabric MP-BGP EVPN, Multi-Site eBGP EVPN between sites over VRF DCI, cross-site host checks, a short optimisation closer |

Lab 4 is the from-scratch fabric build: connected underlay only, then MP-BGP EVPN inside each site and between sites.

## Connecting to the devices

The Lab 4 workbook covers the CML web console, the CML Breakout Tool, SSH to the CML console server (`open /<lab>/<node>/0`), and SSH over the out-of-band management network.

## What is not in this repository

The CML YAML files, startup configurations, workbooks, grader and answer key are not committed here. This repository stays a small, rendered network-as-code example with no device passwords and no lab keys.
