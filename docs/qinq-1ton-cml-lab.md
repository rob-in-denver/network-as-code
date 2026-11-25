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

## Appendix — CLI config notes

Annotated snippets for every role in this lab. Commands that matter are explained in place. These are the patterns the grader looks for, not a substitute for the full start and solved configs.

Replace `n` with the site number (1–6). Customer A S-VLAN is `1100+n`; customer B is `2100+n`. The IKEv2 pre-shared key is shown as `<PSK>`. Do not publish a real key or device password.

### A. Access switch (`ACCn`) — `dot1q-tunnel` UNIs

The access switch is an L3 IOL-L2 device. Customer ports are tunnel (QinQ) access ports: the switch pushes one S-tag and leaves the customer's C-tag untouched. The uplink to the aggregation switch is an 802.1Q trunk that carries only this site's S-VLANs and the management VLAN.

```
no spanning-tree vlan 1101-1106,2101-2106,999
vlan 1101
vlan 2101
vlan 999
!
interface Ethernet0/1
 description NNI to AGG1 (or AGG2)
 switchport trunk encapsulation dot1q
 switchport trunk allowed vlan 999,1101,2101
 switchport mode trunk
 no shutdown
!
interface Ethernet0/2
 description UNI to CEAn — customer A, S-VLAN 1101
 switchport access vlan 1101
 switchport mode dot1q-tunnel
 spanning-tree bpdufilter enable
 no cdp enable
 no shutdown
!
interface Ethernet0/3
 description UNI to CEBn — customer B, S-VLAN 2101
 switchport access vlan 2101
 switchport mode dot1q-tunnel
 spanning-tree bpdufilter enable
 no cdp enable
 no shutdown
```

| Command | What it does |
|---|---|
| `switchport access vlan 1101` | The **S-VLAN** this UNI belongs to. On a tunnel port this is the outer tag the switch pushes, not a customer VLAN. |
| `switchport mode dot1q-tunnel` | Makes the port a QinQ UNI. Ingress C-tagged (or untagged) frames get an S-tag; egress pops the S-tag only. |
| `spanning-tree bpdufilter enable` | Drops BPDUs on the UNI so a customer STP domain cannot influence the provider, and so customer BPDUs are not forwarded into the S-VLAN. |
| `no cdp enable` | Stops CDP on the UNI. `l2protocol-tunnel` was not verified on IOL-L2 in this build, so the lab filters L2 protocols instead of tunnelling them. |
| `switchport trunk allowed vlan 999,1101,2101` | Prunes the uplink to this site's S-VLANs plus management. Do not leave the trunk at the default (all VLANs). |
| `no spanning-tree vlan …` | Turns Rapid-PVST off for the S-VLANs. See the AGG notes. |

**MTU caveat.** IOL-L2 has no `system mtu` command, so the NNI cannot be raised. A double-tagged frame is 1500 + 4 (C-tag) + 4 (S-tag) = 1508 bytes on the wire. A 1496-byte DF ping from a CE succeeds; a 1500-byte DF ping fails. In production you would raise the NNI MTU to at least 1508 (often 1512 or 9216). The DMVPN overlay uses `ip mtu 1400` / `ip tcp adjust-mss 1360` on Tunnel0 so GRE and IPsec fit inside that 1496-byte path.

**Gotchas**

* IOL-L2 has no selective QinQ and no `switchport vlan mapping`. The 1:N C-VLAN-to-S-VLAN mapping cannot be done here; it lives on the IOL-XE PE.
* VLANs 1002–1005 are reserved on IOL-L2. Do not use them as S-VLANs.
* The UNI must be an access port in the S-VLAN **and** `dot1q-tunnel`. A trunk UNI would expect the customer to send the S-tag.
* Forgetting `no shutdown` on the UNI leaves the CE isolated. The start-state UNIs are shut.

**Verification**

```
ACC1# show dot1q-tunnel
ACC1# show interfaces Ethernet0/2 switchport
  ! Operational Mode: tunnel
  ! Access Mode VLAN: 1101
ACC1# show interfaces trunk
CEA1# ping 10.100.0.254 size 1496 df-bit
CEA1# ping 10.100.0.254 size 1500 df-bit    ! expected to fail on IOL-L2
```

### B. Aggregation (`AGG1`, `AGG2`) — S-VLAN trunks, PVST off

Each AGG is a pure S-VLAN bridge, dual-homed to PE1 (customer A) and PE2 (customer B). There is no AGG-to-AGG link. Trunks are pruned so each uplink only carries the VLANs that belong on it.

```
no spanning-tree vlan 1101-1106,2101-2106,999
!
interface Ethernet0/1
 description NNI to PE1 (customer A)
 switchport trunk encapsulation dot1q
 switchport trunk allowed vlan 999,1101,1102,1103    ! AGG1; AGG2 uses 999,1104-1106
 switchport mode trunk
 no shutdown
!
interface Ethernet0/2
 description NNI to PE2 (customer B)
 switchport trunk encapsulation dot1q
 switchport trunk allowed vlan 2101,2102,2103        ! AGG1; no VLAN 999 on PE2 links
 switchport mode trunk
 no shutdown
```

| Command | What it does |
|---|---|
| `no spanning-tree vlan 1101-1106,2101-2106,999` | Disables Rapid-PVST for every provider VLAN. The topology is a loop-free tree by construction (no AGG-AGG link, no PE-PE link). On IOL-L2, Rapid-PVST with many S-VLANs produced continuous topology-change storms and broke sites 4–6. Do not put these VLANs back under PVST, and do not add a link between AGG1 and AGG2. |
| `switchport trunk allowed vlan 999,1101-1103` | On the PE1 link: customer A S-VLANs for this AGG's sites, plus management. |
| `switchport trunk allowed vlan 2101-2103` | On the PE2 link: customer B S-VLANs only. VLAN 999 is carried only toward PE1, so BDI999 on PE1 can join AGG1 and AGG2 without creating a loop through PE2. PE2 is managed over OOB only. |

**Gotchas**

* A default (unpruned) trunk does not break forwarding — PE EFPs simply do not match the wrong S-VLAN — but it floods frames to the wrong PE and wastes bandwidth.
* If you allow VLAN 999 on both PE uplinks and also enable STP, you have built a loop. Keep 999 off the PE2 links.

**Verification**

```
AGG1# show interfaces trunk
  ! Et0/1  999,1101-1103
  ! Et0/2  2101-2103
AGG2# show interfaces trunk
  ! Et0/1  999,1104-1106
  ! Et0/2  2104-2106
AGG1# show spanning-tree vlan 1101
  ! no spanning tree info (STP is off)
```

### C. PE routers (`PE1`, `PE2`) — EVC service instances and the 1:N mapping

This is the core of the lab. HQ-A sends **one** C-VLAN. PE1 has one Ethernet Flow Point (EFP) per site that matches `S-VLAN + C-VLAN`, pops both tags into a bridge domain, and on egress pushes both tags again (`symmetric`). One C-VLAN therefore fans out to six S-VLANs.

Customer A (PE1):

* C-VLAN 100 → bridge-domain 100, **E-Tree**. Site EFPs are in `split-horizon group 1`; the HQ UNI is not. Leaves can reach the root, not each other.
* C-VLAN 200 → bridge-domain 200, **E-LAN**. No split horizon. Customer OSPF 100 runs here (the DMVPN underlay).
* Site 6's E-Tree C-VLAN is 110 locally; the EFP matches 110 and pops into the same BD 100, which is the 110-to-100 translation.
* VLAN 999 is a single-tag EFP into BDI999 (SP management, OSPF 1).

Customer B (PE2) is the same idea with S-VLANs 2101–2106 and one E-LAN in bridge-domain 300. There is no split horizon and no second C-VLAN.

```
! PE1 NNI toward AGG1 (sites 1–3). Ethernet0/3 toward AGG2 repeats this for sites 4–6.
interface Ethernet0/1
 description NNI to AGG1 (S-tagged)
 no ip address
 no shutdown
 service instance 999 ethernet
  encapsulation dot1q 999
  rewrite ingress tag pop 1 symmetric
  bridge-domain 999
 service instance 101 ethernet
  description site 1 E-Tree leaf
  encapsulation dot1q 1101 second-dot1q 100
  rewrite ingress tag pop 2 symmetric
  bridge-domain 100 split-horizon group 1
 service instance 201 ethernet
  description site 1 E-LAN
  encapsulation dot1q 1101 second-dot1q 200
  rewrite ingress tag pop 2 symmetric
  bridge-domain 200
!
! HQ UNI — single C-tag, no S-tag, not in a split-horizon group (E-Tree root)
interface Ethernet0/2
 description UNI to HQ-A
 no ip address
 no shutdown
 service instance 100 ethernet
  encapsulation dot1q 100
  rewrite ingress tag pop 1 symmetric
  bridge-domain 100
 service instance 200 ethernet
  encapsulation dot1q 200
  rewrite ingress tag pop 1 symmetric
  bridge-domain 200
!
! Site 6 E-Tree on the AGG2 NNI: match local C-VLAN 110, land in the same BD 100
interface Ethernet0/3
 service instance 106 ethernet
  encapsulation dot1q 1106 second-dot1q 110
  rewrite ingress tag pop 2 symmetric
  bridge-domain 100 split-horizon group 1
!
interface BDI999
 description SP management (BD 999 joins AGG1 and AGG2)
 ip address 10.255.0.1 255.255.255.0
 ip ospf priority 255
 no shutdown
```

| Command | What it does |
|---|---|
| `encapsulation dot1q 1101 second-dot1q 100` | Matches only frames whose outer tag is S-VLAN 1101 and whose inner tag is C-VLAN 100. That is the 1:N mapping: the same C-VLAN 100 is matched by six EFPs, each with a different S-VLAN. |
| `rewrite ingress tag pop 2 symmetric` | Ingress: pop S-tag and C-tag, then bridge the payload in the BD. Egress (`symmetric`): push the same two tags back, so the site ACC sees its S-VLAN and the CE sees its C-VLAN. |
| `bridge-domain 100 split-horizon group 1` | Puts the site EFP in split-horizon group 1 of BD 100. Members of the same group do not forward to each other, which is the E-Tree leaf behaviour. |
| `bridge-domain 100` (HQ UNI, no group) | The root is outside the group, so it can reach every leaf, and every leaf can reach it, but leaves cannot reach each other. |
| `encapsulation dot1q 1106 second-dot1q 110` | Site 6's E-Tree EFP. Because both tags are popped into BD 100, a frame that arrived as S1106/C110 is sent toward HQ-A as a single C-tag 100. The other direction is the reverse rewrite. |
| `encapsulation dot1q 100` + `pop 1` on the HQ UNI | HQ-A does not send an S-tag. Pop one tag into the same bridge domain the site EFPs use. |
| `interface BDI999` | Routed interface for bridge-domain 999. PE1 is the OSPF DR on the management VLAN (`ip ospf priority 255`). |

**Gotchas**

* Forgetting `symmetric` means return traffic is not re-tagged and the CE never sees its C-VLAN.
* Putting the HQ UNI in `split-horizon group 1` isolates the hub from every leaf.
* Taking one site EFP *out* of the group lets that site reach every other leaf (and every leaf reach it).
* `second-dot1q` has to match what the CE actually sends. Change CEA3 to C-VLAN 101 and instance 101's `Pkts In` stops incrementing — the frame matches no EFP and is dropped on the NNI.
* IOL-XE will boot into the setup dialog if a physical Ethernet interface has neither `ip address` nor `no ip address` in the startup config. Unused ports need `no ip address` and `shutdown`.
* PE2 has no BDI999 and is managed over OOB only.

**Verification**

```
PE1# show bridge-domain 100
  ! service instances 100 (HQ) and 101–106 (sites)
PE1# show ethernet service instance id 106 interface Ethernet0/3 detail
  ! Encapsulation: dot1q 1106 … second-dot1q 110
  ! Rewrite: ingress tag pop 2 symmetric
PE1# show ethernet service instance stats
CEA1# ping 10.100.0.254            ! E-Tree leaf → root: succeeds
CEA1# ping 10.100.0.2              ! E-Tree leaf → leaf: fails (split horizon)
CEA1# ping 10.200.0.5              ! E-LAN any-to-any: succeeds
CEA6# ping 10.100.0.254            ! C-VLAN 110 translated to 100: succeeds
CEA2# ping 10.1.6.1 source Loopback0
```

### D. DMVPN hub (`HQ-DMVPN`) — mGRE, NHRP, IKEv2, eBGP policy

The underlay is customer A's E-LAN (C-VLAN 200, OSPF 100). HQ-A Ethernet0/2 (`10.0.254.1/30`) and the hub Ethernet0/1 (`10.0.254.2/30`) join that OSPF, so the hub learns every spoke NBMA address (`10.1.n.1`). Spoke and HQ LANs stay out of OSPF.

```
interface Loopback0
 ip address 10.1.254.1 255.255.255.255    ! NBMA / tunnel source, in OSPF 100
interface Loopback10
 ip address 10.50.1.1 255.255.255.0       ! HQ LAN, BGP only
interface Loopback11
 ip address 10.50.2.1 255.255.255.0
!
router ospf 100
 router-id 10.1.254.1
 passive-interface default
 no passive-interface Ethernet0/1
 network 10.1.254.1 0.0.0.0 area 0
 network 10.0.254.0 0.0.0.3 area 0        ! do not advertise 10.50.0.0/16 or 10.99.0.0/24
!
crypto ikev2 proposal DMVPN-PROP
 encryption aes-cbc-256
 integrity sha256
 group 14
crypto ikev2 policy DMVPN-POL
 proposal DMVPN-PROP
crypto ikev2 keyring DMVPN-KR
 peer ANY
  address 0.0.0.0 0.0.0.0
  pre-shared-key <PSK>
crypto ikev2 profile DMVPN-IKEV2
 match identity remote address 0.0.0.0
 authentication remote pre-share
 authentication local pre-share
 keyring local DMVPN-KR
crypto ipsec transform-set DMVPN-TS esp-aes 256 esp-sha256-hmac
 mode transport
crypto ipsec profile DMVPN-IPSEC
 set transform-set DMVPN-TS
 set ikev2-profile DMVPN-IKEV2
!
interface Tunnel0
 description DMVPN Phase 1 hub (mGRE)
 ip address 10.99.0.254 255.255.255.0
 no ip redirects
 ip mtu 1400
 ip tcp adjust-mss 1360
 ip nhrp network-id 1
 ip nhrp map multicast dynamic
 tunnel source Loopback0
 tunnel mode gre multipoint
 tunnel key 1
 tunnel protection ipsec profile DMVPN-IPSEC
!
ip prefix-list HUB-TO-SPOKE seq 10 permit 0.0.0.0/0
ip prefix-list HUB-TO-SPOKE seq 20 permit 10.50.0.0/16
ip prefix-list SPOKE-LANS seq 10 permit 172.16.0.0/16 ge 24 le 24
!
router bgp 65000
 bgp router-id 10.1.254.1
 neighbor 10.99.0.1 remote-as 65101
 ! … 10.99.0.2 65102 through 10.99.0.6 65106 (static neighbors; alternate-as allows only five ASes)
 address-family ipv4
  network 10.50.1.0 mask 255.255.255.0
  network 10.50.2.0 mask 255.255.255.0
  aggregate-address 10.50.0.0 255.255.0.0 summary-only
  neighbor 10.99.0.1 activate
  neighbor 10.99.0.1 default-originate
  neighbor 10.99.0.1 prefix-list SPOKE-LANS in
  neighbor 10.99.0.1 prefix-list HUB-TO-SPOKE out
  ! repeat for .2 – .6
```

| Command | What it does |
|---|---|
| `tunnel mode gre multipoint` | Makes Tunnel0 an **mGRE** hub that can have many GRE destinations on one interface. This is the only mGRE tunnel in the lab. |
| `ip nhrp network-id 1` / `ip nhrp map multicast dynamic` | NHRP network-id must match the spokes. `map multicast dynamic` lets the hub replicate multicast (for example NHRP) to registered spokes. |
| `tunnel key 1` | Must match on hub and spokes; a mismatched key means the GRE header is ignored. |
| `tunnel protection ipsec profile DMVPN-IPSEC` | Encrypts the GRE transport with IKEv2/IPsec. `mode transport` is the usual DMVPN choice (the outer IP header is the tunnel source/destination; GRE is the payload). |
| `pre-shared-key <PSK>` | Lab placeholder. The same key is on every DMVPN node. |
| `aggregate-address 10.50.0.0 255.255.0.0 summary-only` | Advertises the HQ aggregate and marks the contributing /24s suppressed (`s>` in `show ip bgp`), so they are not eligible to send. |
| `default-originate` | Sends `0.0.0.0/0` to that neighbor even if the hub has no default in its own RIB. |
| `prefix-list HUB-TO-SPOKE out` | Second safety net: only `0/0` and `10.50.0.0/16` leave toward a spoke. Spokes never learn each other's `172.16.n.0/24`. |
| `prefix-list SPOKE-LANS in` | Accepts only `172.16.0.0/16` with mask `/24`. |
| No `ip nhrp redirect` | Phase 1: the hub must not tell spokes to build shortcuts. Combined with p2p GRE on the spokes, there is no direct spoke-to-spoke tunnel. |

Spoke-to-spoke traffic is **allowed** but always hairpins through the hub on the default route. To forbid it entirely you would filter on the hub (for example an ACL on Tunnel0); that is not done here.

**Gotchas**

* Do not put Loopback10/11 or Tunnel0 into OSPF 100. If the hub's NBMA address (`10.1.254.1/32`) is ever learned *via the tunnel*, the tunnel goes down with `%TUN-5-RECURDOWN`.
* `alternate-as` on a listen range allows at most five AS numbers, so this lab uses six static neighbors.
* A missing `tunnel key` or a different NHRP network-id on one side gives a tunnel that is up with no NHRP registration.

**Verification**

```
HQ-A# show ip ospf neighbor                 ! 10.1.254.1 FULL
HQ-DMVPN# show ip route 10.1.6.1            ! Known via "ospf 100"
HQ-DMVPN# show interfaces Tunnel0           ! Tunnel protocol/transport multi-GRE/IP
HQ-DMVPN# show dmvpn                        ! Type:Hub, NHRP Peers:6, all UP, Attrb D
HQ-DMVPN# show ip nhrp
HQ-DMVPN# show crypto ikev2 sa              ! six READY SAs
HQ-DMVPN# show ip bgp summary               ! six neighbors, PfxRcd 1 each
HQ-DMVPN# show ip bgp                       ! *> 10.50.0.0/16, s> for the /24s, six 172.16.n.0/24
HQ-A# show ip route 172.16.1.0              ! % Subnet not in table (underlay stays clean)
```

### E. Spokes (`CEA1`–`CEA6`) — point-to-point GRE, NHRP, eBGP

Each existing customer-A CE is the spoke for its site. Loopback0 `10.1.n.1` is already in OSPF 100 and is the tunnel source (NBMA). Loopback1 `172.16.n.1/24` is the spoke LAN and is advertised only in BGP.

The IKEv2 and IPsec configuration is identical to the hub. The tunnel is not.

```
interface Loopback1
 description Site 1 spoke LAN (overlay, eBGP only)
 ip address 172.16.1.1 255.255.255.0
!
interface Tunnel0
 description DMVPN Phase 1 spoke (point-to-point GRE to HQ-DMVPN)
 ip address 10.99.0.1 255.255.255.0
 no ip redirects
 ip mtu 1400
 ip tcp adjust-mss 1360
 ip nhrp map 10.99.0.254 10.1.254.1
 ip nhrp network-id 1
 ip nhrp nhs 10.99.0.254
 tunnel source Loopback0
 tunnel destination 10.1.254.1          ! p2p GRE — do not use gre multipoint
 tunnel key 1
 tunnel protection ipsec profile DMVPN-IPSEC
!
ip prefix-list SPOKE-LAN-OUT seq 10 permit 172.16.1.0/24
!
router bgp 65101
 bgp router-id 10.1.1.1
 neighbor 10.99.0.254 remote-as 65000
 address-family ipv4
  network 172.16.1.0 mask 255.255.255.0
  neighbor 10.99.0.254 activate
  neighbor 10.99.0.254 prefix-list SPOKE-LAN-OUT out
```

| Command | What it does |
|---|---|
| `tunnel destination 10.1.254.1` | This is a **point-to-point GRE** tunnel (default `tunnel mode gre ip`). Every packet is encapsulated to the hub's NBMA address. There is no second destination, so a spoke cannot build a spoke-to-spoke tunnel even if it learned another NBMA address. |
| `ip nhrp map 10.99.0.254 10.1.254.1` | Static NHRP mapping of the hub's tunnel address to its NBMA address. On a p2p spoke this is how the spoke finds the hub. |
| `ip nhrp nhs 10.99.0.254` | Next-hop server: the spoke registers with the hub and uses it to resolve other addresses. In Phase 1 it will only ever resolve the hub. |
| No `ip nhrp shortcut` | A Phase 1 spoke must not install shortcut NHRP mappings. |
| `network 172.16.1.0` + `prefix-list SPOKE-LAN-OUT out` | Advertises only this site's LAN. Do not redistribute OSPF into BGP. |
| Unique AS `65100+n` | Makes the origin visible in the AS path and avoids `allowas-in`. |

On HQ-A, one OSPF statement is also required so the /30 is advertised: `no passive-interface Ethernet0/2` and `network 10.0.254.0 0.0.0.3 area 0`.

**Gotchas**

* `tunnel mode gre multipoint` on a spoke is Phase 2/3 and is wrong for this lab. `show interfaces Tunnel0` must show `GRE/IP` on a spoke and `multi-GRE/IP` on the hub.
* If OSPF 100 or C-VLAN 200 breaks, the tunnel destination is unreachable and every overlay session dies.
* Do not advertise `10.1.n.1` or `10.1.254.1` into BGP. The tunnel destination must remain an OSPF /32 so it wins over the BGP default (longest match). That is what prevents recursive routing.

**Verification**

```
CEA1# show interfaces Tunnel0 | include protocol/transport
  ! GRE/IP
CEA1# show dmvpn
  ! Type:Spoke, NHRP Peers:1, hub 10.1.254.1 / 10.99.0.254 UP, Attrb S
CEA1# show ip bgp
  ! only 0.0.0.0, 10.50.0.0/16 (next hop 10.99.0.254) and 172.16.1.0/24
CEA1# ping 10.50.1.1 source Loopback1
CEA1# traceroute 172.16.4.1 source Loopback1 numeric
  ! 1 10.99.0.254   (hub)
  ! 2 10.99.0.4     (CEA4, via its own spoke tunnel — hairpin, not a direct tunnel)
CEA1# show ip nhrp
  ! still only 10.99.0.254 — no entry for 10.99.0.4 after the traceroute
CEA2# show ip route 10.1.254.1
  ! Known via "ospf 100"  (not via the BGP default)
```

