# QinQ 1:N lab with a DMVPN Phase 1 overlay (Cisco Modeling Labs)

This page is a public summary of a separate Cisco Modeling Labs practice lab for 802.1Q tunneling (QinQ) with one customer C-VLAN mapped to many provider S-VLANs, extended with a DMVPN Phase 1 hub-and-spoke overlay running eBGP on top of the QinQ service. The CML files, startup and solution configurations, workbook, grader and answer key are not published in this repository.

## Design

- **Six edge sites.** Each site has an IOL-L2 L3 access switch with two `switchport mode dot1q-tunnel` user ports (one per customer, each in its own S-VLAN) and a customer router per tunnel port.
- **Aggregation.** Two IOL-L2 switches bridge the S-VLANs. Each is dual-homed to the two service-edge routers. The S-VLAN topology is a loop-free tree with no inter-aggregation link and spanning tree off for the S-VLANs, because Rapid-PVST on IOL-L2 produced endless topology-change storms.
- **The 1:N mapping lives on the core side.** Two IOL-XE service-edge routers hold one Ethernet Flow Point per site. Each one matches `dot1q <S-VLAN> second-dot1q <C-VLAN>`, applies `rewrite ingress tag pop 2 symmetric` and joins a bridge domain. One hub C-VLAN (100) therefore fans out to six S-VLANs, and the same S-VLANs also carry a second C-VLAN (200).
- **Services.** An E-Tree (split-horizon bridge domain, hub to branches only), an E-LAN running customer OSPF, a branch that uses a different local C-VLAN (110) translated to 100, and a second customer that reuses C-VLAN 100 and the same IPv4 subnet in its own set of S-VLANs.

## DMVPN Phase 1 extension

- **Underlay.** The first customer's E-LAN (C-VLAN 200, OSPF) is the transport. A new IOL-XE HQ hub router joins that OSPF on a link to the customer's HQ router, so every branch router loopback (the NBMA address) is advertised to it.
- **Overlay.** The hub runs an mGRE tunnel; the six branch routers are point-to-point GRE spokes with a fixed tunnel destination and NHRP registration. IKEv2 with IPsec transport mode protects the tunnels.
- **eBGP.** The hub is one private AS and each spoke has its own private AS. Each spoke advertises only its own /24 LAN. The hub sends spokes only a default route (`default-originate`) and one HQ aggregate (`aggregate-address ... summary-only`), enforced with outbound prefix-lists.
- **No direct spoke-to-spoke.** Spokes never learn another spoke's route or NHRP mapping, and there is no NHRP redirect or shortcut. Spoke-to-spoke traffic hairpins through the hub on the default route; a traceroute shows the hub tunnel address as the first hop and the spoke's NHRP cache still lists only the hub.
- **Underlay and overlay stay apart.** Spoke and HQ LANs and the tunnel subnet never enter the underlay OSPF, and BGP carries no underlay prefix, so the tunnel destination is always an OSPF host route and the tunnel cannot recurse through itself.

## Why IOL

IOL-L2 accepts `switchport mode dot1q-tunnel` and the CML dataplane carries double-tagged frames; a packet capture of the access link shows S-tag 1101 with C-tag 100 (and C-tag 200). IOL-L2 has no selective QinQ or VLAN mapping, so IOL-XE EVCs do the one-to-many mapping. IOL nodes need about 1 GB each, so 25 licensed nodes use roughly 25 GB of RAM, well inside a 40-node Personal Plus license.

## Verification

The lab guide checks `show dot1q-tunnel`, `show interfaces trunk`, `show bridge-domain`, `show ethernet service instance` (EFP encapsulation, rewrite and per-instance counters), ping tests that succeed and fail by design (split horizon), a capture on the access link that decodes the S-tag and C-tag of every frame, and for the overlay `show dmvpn`, `show ip nhrp`, `show crypto ikev2 sa`, `show ip bgp`, `show ip route bgp` and a spoke-to-spoke traceroute through the hub.

## What is not in this repository

The CML YAML file, device configurations, workbook, grader and answer key are not committed here. This repository stays a small, rendered network-as-code example with no device passwords and no lab keys.
