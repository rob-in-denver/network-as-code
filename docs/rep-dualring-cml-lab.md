# Cisco REP dual-ring lab (Cisco Modeling Labs)

This page is a public summary of a separate CCIE-style Cisco Modeling Labs practice lab for Resilient Ethernet Protocol (REP). The CML files, startup and solution configurations, workbook, grader and answer key are not published in this repository.

## Why Catalyst 9000v

IOL-L2 and IOSvL2 do not implement REP (`rep segment` is not accepted). The lab therefore uses the Catalyst 9000v Q200 image (IOS XE 17.15, 4 vCPU and 12 GB RAM per node) for every REP-participating switch. Six IOL-L2 switches provide the STP domain and a non-REP legacy path. That mix stays near 80 GB of RAM and 16 licensed nodes, inside a 40-node Personal Plus license and a roughly 96 GB “one lab at a time” budget.

## Topology

Two open REP segments run as parallel rings across the same six Catalyst 9000v switches:

- **Segment 100:** DIST1 (primary edge, preferred) — ACC1 — ACC2 — ACC3 — ACC4 — DIST2 (secondary edge).
- **Segment 200:** the same six switches on a second set of trunks; DIST1 is the primary edge and DIST2 is preferred, so VLAN load balancing does not elect the same block point on both rings.
- **Segment 50:** no-neighbor edges on DIST1 and DIST2, with two IOL-L2 closets (LEG1, LEG2) in the middle.
- **STP domain:** CORE1 (root), CORE2, and an island (STP1, STP2). The REP edges send STCNs toward STP.
- **Hosts:** four Alpine Linux endpoints in VLANs 10, 20, 30 and 40, with HSRP gateways on DIST1/DIST2, used for failover and VLAN load-balancing checks.
- Out-of-band management on 192.168.255.0/24.

The imported lab starts with VLANs, trunks, HSRP and Rapid-PVST only. The candidate then adds the admin VLAN, LSL timers, both rings, VLAN load balancing with preempt delay, STCN, no-neighbor edges, and failover tests (`show rep topology` / `show rep topology detail`). The intended length is about two hours.

## Connecting to the devices

The workbook covers the CML web console, the CML Breakout Tool, SSH to the CML console server (`open /<lab>/<node>/0`), and SSH over the out-of-band management network.

## What is not in this repository

The CML YAML file, device configurations, workbook, grader and answer key are not committed here. This repository stays a small, rendered network-as-code example with no device passwords and no lab keys.
