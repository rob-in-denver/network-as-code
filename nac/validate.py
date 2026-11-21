"""Validate rendered IOS-XE and NX-OS against the YAML source of truth.

This module never opens a socket. Live collection, if you add it, belongs in
nac.collect and stays out of CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(?i)\b(password|secret|cisco123|admin123)\b")
PSK_LINE = re.compile(r"(?:pre-shared-key|ip nhrp authentication)\s+(\S+)")


def load_yaml(path: Path) -> dict:
    with path.open() as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a mapping")
    return data


def stripped_lines(config: str) -> set[str]:
    return {line.strip() for line in config.splitlines() if line.strip()}


def require_line(config: str, needle: str, findings: list[str], device: str) -> None:
    if needle not in stripped_lines(config):
        findings.append(f"{device}: missing line: {needle}")


def check_secrets(config: str, device: str, placeholder: str) -> list[str]:
    findings: list[str] = []
    if SECRET.search(config):
        findings.append(f"{device}: forbidden credential-like token")
    for match in PSK_LINE.finditer(config):
        if match.group(1) != placeholder:
            findings.append(f"{device}: key material is not the documented placeholder")
    return findings


def check_nxos(device: dict, fabric: dict, config: str) -> list[str]:
    findings: list[str] = []
    name = device["hostname"]
    site = next(item for item in fabric["sites"] if item["id"] == device["site"])
    require_line(config, f"hostname {name}", findings, name)
    require_line(config, "feature ospf", findings, name)
    require_line(config, "feature bgp", findings, name)
    require_line(config, "nv overlay evpn", findings, name)
    require_line(config, f"ip address {device['router_id']}/32", findings, name)
    require_line(config, f"router ospf {fabric['ospf_process']}", findings, name)
    require_line(config, f"router-id {device['router_id']}", findings, name)
    require_line(config, f"router bgp {site['asn']}", findings, name)
    require_line(config, "passive-interface default", findings, name)

    for iface in device["interfaces"]:
        require_line(config, f"interface {iface['name']}", findings, name)
        require_line(config, f"description {iface['description']}", findings, name)
        require_line(config, f"ip address {iface['address']}/{iface['prefix']}", findings, name)
        require_line(config, f"mtu {fabric['mtu']}", findings, name)
        if iface["role"] == "underlay":
            require_line(config, "ip ospf network point-to-point", findings, name)
            require_line(config, f"ip router ospf {fabric['ospf_process']} area {fabric['ospf_area']}", findings, name)
        if iface["role"] == "dci":
            require_line(config, "evpn multisite dci-tracking", findings, name)
            require_line(config, f"neighbor {iface['peer_address']}", findings, name)
            require_line(config, f"remote-as {iface['peer_as']}", findings, name)
            require_line(config, "rewrite-evpn-rt-asn", findings, name)

    if device["role"] == "spine":
        require_line(config, "retain route-target all", findings, name)
        if "interface nve1" in config:
            findings.append(f"{name}: spine must not be a VTEP")
        clients = [item for item in fabric["devices"] if item["site"] == device["site"] and item["role"] != "spine"]
        if config.count("route-reflector-client") < len(clients):
            findings.append(f"{name}: expected {len(clients)} route-reflector clients")
        for client in clients:
            require_line(config, f"neighbor {client['router_id']}", findings, name)
    else:
        if "route-reflector-client" in config:
            findings.append(f"{name}: route-reflector-client belongs on spines")
        if "retain route-target all" in config:
            findings.append(f"{name}: retain route-target all belongs on spines")
        for spine in [item for item in fabric["devices"] if item["site"] == device["site"] and item["role"] == "spine"]:
            require_line(config, f"neighbor {spine['router_id']}", findings, name)

    if device["role"] in {"leaf", "bgw"}:
        require_line(config, "feature nv overlay", findings, name)
        require_line(config, f"ip address {device['vtep']}/32", findings, name)
        require_line(config, "interface nve1", findings, name)
        require_line(config, "host-reachability protocol bgp", findings, name)
        require_line(config, "source-interface loopback1", findings, name)
        for vni in fabric["vnis"]:
            require_line(config, f"vn-segment {vni['id']}", findings, name)
            if vni["type"] == "l2":
                require_line(config, f"member vni {vni['id']}", findings, name)
                require_line(config, "ingress-replication protocol bgp", findings, name)
            else:
                require_line(config, f"member vni {vni['id']} associate-vrf", findings, name)

    if device["role"] == "leaf":
        require_line(config, f"fabric forwarding anycast-gateway-mac {fabric['anycast_gateway_mac']}", findings, name)
        for vni in fabric["vnis"]:
            if vni["type"] != "l2":
                continue
            require_line(config, f"interface Vlan{vni['vlan']}", findings, name)
            require_line(config, f"ip address {vni['gateway']}/{vni['prefix']}", findings, name)
            require_line(config, "fabric forwarding mode anycast-gateway", findings, name)
        for port in device.get("host_ports", []):
            require_line(config, f"interface {port['name']}", findings, name)
            require_line(config, f"switchport access vlan {port['vlan']}", findings, name)

    if device["role"] == "bgw":
        require_line(config, f"evpn multisite border-gateway {site['multisite_id']}", findings, name)
        require_line(config, "multisite border-gateway interface loopback100", findings, name)
        require_line(config, f"ip address {site['multisite_vip']}/32", findings, name)
        require_line(config, "multisite ingress-replication", findings, name)
    elif "evpn multisite border-gateway" in config:
        findings.append(f"{name}: multisite border-gateway belongs on BGWs")

    return findings


def check_dmvpn(device: dict, dmvpn: dict, config: str) -> list[str]:
    findings: list[str] = []
    name = device["hostname"]
    placeholder = dmvpn["psk_placeholder"]
    findings.extend(check_secrets(config, name, placeholder))
    require_line(config, f"hostname {name}", findings, name)
    require_line(config, f"vrf definition {dmvpn['fvrf']}", findings, name)
    require_line(config, f"vrf definition {dmvpn['ivrf']}", findings, name)
    require_line(config, f"crypto ikev2 proposal {dmvpn['ike']['proposal']}", findings, name)
    require_line(config, f"encryption {dmvpn['ike']['encryption']}", findings, name)
    require_line(config, f"match fvrf {dmvpn['fvrf']}", findings, name)
    require_line(config, f"ivrf {dmvpn['ivrf']}", findings, name)
    require_line(config, f"crypto ipsec profile {dmvpn['ipsec']['profile']}", findings, name)
    require_line(config, "mode transport", findings, name)
    require_line(config, f"vrf forwarding {dmvpn['fvrf']}", findings, name)
    require_line(config, f"vrf forwarding {dmvpn['ivrf']}", findings, name)
    require_line(config, "tunnel mode gre multipoint", findings, name)
    require_line(config, f"tunnel vrf {dmvpn['fvrf']}", findings, name)
    require_line(config, f"tunnel protection ipsec profile {dmvpn['ipsec']['profile']}", findings, name)
    require_line(config, f"ip nhrp network-id {dmvpn['nhrp']['network_id']}", findings, name)
    require_line(config, f"ip address {device['tunnel_address']} {dmvpn['tunnel_mask']}", findings, name)
    require_line(config, f"router eigrp {dmvpn['eigrp']['name']}", findings, name)
    require_line(
        config,
        f"address-family ipv4 unicast vrf {dmvpn['ivrf']} autonomous-system {dmvpn['eigrp']['asn']}",
        findings,
        name,
    )
    require_line(config, f"ip route vrf {dmvpn['fvrf']} 0.0.0.0 0.0.0.0 {device['wan_gateway']}", findings, name)

    if device["role"] == "hub":
        require_line(config, "ip nhrp map multicast dynamic", findings, name)
        require_line(config, "ip nhrp redirect", findings, name)
        require_line(config, "no next-hop-self", findings, name)
        require_line(config, "no split-horizon", findings, name)
        if "ip nhrp shortcut" in config:
            findings.append(f"{name}: hub should not install NHRP shortcuts")
        for spoke in dmvpn["spokes"]:
            require_line(config, f"ip prefix-list PFX-{spoke['hostname']} seq 10 permit {spoke['lan_prefix']}", findings, name)
            require_line(
                config,
                f"distribute-list prefix PFX-{spoke['hostname']} gateway GW-{spoke['hostname']} in",
                findings,
                name,
            )
    else:
        require_line(config, "ip nhrp shortcut", findings, name)
        require_line(config, "distribute-list prefix LAN-OUT out", findings, name)
        require_line(config, f"ip prefix-list LAN-OUT seq 10 permit {device['lan_prefix']}", findings, name)
        if "ip nhrp map multicast dynamic" in config:
            findings.append(f"{name}: spokes must not be an NHRP multicast hub")
        for hub in dmvpn["hubs"]:
            require_line(config, f"ip nhrp map {hub['tunnel_address']} {hub['nbma']}", findings, name)
            require_line(config, f"ip nhrp nhs {hub['tunnel_address']}", findings, name)

    return findings


def link_findings(fabric: dict) -> list[str]:
    findings: list[str] = []
    by_name = {device["hostname"]: device for device in fabric["devices"]}
    seen: set[str] = set()
    vips = {site["multisite_vip"] for site in fabric["sites"]}
    addresses: dict[str, str] = {}

    for device in fabric["devices"]:
        if device["hostname"] in seen:
            findings.append(f"{device['hostname']}: duplicate hostname")
        seen.add(device["hostname"])
        addresses.setdefault(device["router_id"], device["hostname"])
        if addresses[device["router_id"]] != device["hostname"]:
            findings.append(f"{device['hostname']}: router-id {device['router_id']} is reused")
        if device["role"] in {"leaf", "bgw"} and "vtep" not in device:
            findings.append(f"{device['hostname']}: VTEP loopback missing")
        for iface in device["interfaces"]:
            addr = iface["address"]
            if addr in vips:
                findings.append(f"{device['hostname']}: interface uses the multisite VIP")
            owner = addresses.get(addr)
            if owner and owner != f"{device['hostname']}:{iface['name']}":
                findings.append(f"{device['hostname']}: address {addr} collides with {owner}")
            addresses[addr] = f"{device['hostname']}:{iface['name']}"
            peer = by_name.get(iface["peer"])
            if peer is None:
                findings.append(f"{device['hostname']}: unknown peer {iface['peer']}")
                continue
            match = [
                item
                for item in peer["interfaces"]
                if item["name"] == iface["peer_interface"] and item["address"] == iface["peer_address"]
            ]
            if not match:
                findings.append(
                    f"{device['hostname']} {iface['name']}: peer {iface['peer']} has no {iface['peer_address']}"
                )
            elif match[0]["peer"] != device["hostname"] or match[0]["peer_address"] != addr:
                findings.append(f"{device['hostname']} {iface['name']}: peer link is not symmetric")
    return findings



IPV6_TOKEN = re.compile(r"(?i)\bipv6\b|::")


def check_enterprise(root: Path, enterprise: dict) -> list[str]:
    findings: list[str] = []
    if not enterprise.get("ipv4_only"):
        findings.append("enterprise_core: ipv4_only must be true")
    placeholder = enterprise["placeholder_token"]

    for p in enterprise["sp_p_routers"]:
        name = p["hostname"]
        path = root / "rendered" / "iosxr" / f"{name}.cfg"
        if not path.exists():
            findings.append(f"{name}: rendered IOS XR config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        require_line(cfg, f"hostname {name}", findings, name)
        require_line(cfg, "neighbor-group RR-CLIENTS", findings, name)
        require_line(cfg, "address-family vpnv4 unicast", findings, name)
        for client in p["clients"]:
            require_line(cfg, f"neighbor {client}", findings, name)

    for pe in enterprise["sp_pe_routers"]:
        name = pe["hostname"]
        path = root / "rendered" / "enterprise" / f"{name}.cfg"
        if not path.exists():
            findings.append(f"{name}: rendered PE config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        require_line(cfg, f"hostname {name}", findings, name)
        require_line(cfg, "mpls ldp router-id Loopback0 force", findings, name)
        require_line(cfg, "neighbor 100.64.0.1 remote-as 65500", findings, name)
        require_line(cfg, "neighbor 100.64.0.2 remote-as 65500", findings, name)
        for vrf in pe["vrfs"]:
            require_line(cfg, f"vrf definition {vrf['name']}", findings, name)

    for rtr in enterprise["dc_routers"]:
        name = rtr["hostname"]
        path = root / "rendered" / "enterprise" / f"{name}.cfg"
        if not path.exists():
            findings.append(f"{name}: rendered DC router config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        require_line(cfg, f"hostname {name}", findings, name)
        require_line(cfg, "router ospf 10", findings, name)
        if rtr["role"] == "dc_dmvpn_hub":
            require_line(cfg, "interface Tunnel10", findings, name)
            require_line(cfg, "ip nhrp redirect", findings, name)
            require_line(cfg, "tunnel vrf INET", findings, name)
            require_line(cfg, "no split-horizon", findings, name)
            require_line(cfg, "no next-hop-self", findings, name)

    for sw in enterprise["dc_switches"]:
        name = sw["hostname"]
        path = root / "rendered" / "enterprise" / f"{name}.cfg"
        if not path.exists():
            findings.append(f"{name}: rendered DC switch config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        require_line(cfg, f"hostname {name}", findings, name)
        require_line(cfg, "vlan 10", findings, name)
        require_line(cfg, "vlan 20", findings, name)

    isp = enterprise["isp"]
    path = root / "rendered" / "enterprise" / f"{isp['hostname']}.cfg"
    if not path.exists():
        findings.append(f"{isp['hostname']}: rendered ISP config missing")
    else:
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, isp["hostname"], placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{isp['hostname']}: IPv6 config is forbidden in IPv4-only core")
        if re.search(r"^router ", cfg, re.M):
            findings.append(f"{isp['hostname']}: the ISP must only carry connected routes")
        for intf in isp["interfaces"]:
            require_line(cfg, f"ip address {intf['address']} {intf['mask']}", findings, isp["hostname"])

    internet_facing = [r["hostname"] for r in enterprise["dc_routers"]
                       if r.get("wan_gateway") or r.get("internet_gateway")]
    if sorted(internet_facing) != ["DC-R1", "DC-R4"]:
        findings.append(f"enterprise_core: exactly DC-R1 and DC-R4 must face the ISP, found {internet_facing}")

    for edge in enterprise["sdwan_edges"]:
        name = edge["hostname"]
        path = root / "rendered" / "sdwan" / f"{name}.cfg"
        if not path.exists():
            findings.append(f"{name}: rendered SD-WAN vEdge config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        if edge["node_definition"] != "cat-sdwan-vedge" or edge["image_definition"] != enterprise["vedge_image"]:
            findings.append(f"{name}: edges must use cat-sdwan-vedge / {enterprise['vedge_image']}")
        for needle in ("#cloud-config", "vinitparam:", "/etc/confd/init/zcloud.xml",
                       "<personality>vedge</personality>", f"<host-name>{name}</host-name>",
                       f"<system-ip>{edge['system_ip']}</system-ip>", "<vpn-id>512</vpn-id>"):
            if needle not in cfg:
                findings.append(f"{name}: missing {needle}")
        require_line(cfg, f"- otp : {placeholder}", findings, name)

    for ctrl in enterprise["sdwan_controllers"]:
        name = ctrl["hostname"]
        path = root / "rendered" / "sdwan" / f"{name}.yaml"
        if not path.exists():
            findings.append(f"{name}: rendered SD-WAN controller config missing")
            continue
        cfg = path.read_text()
        findings.extend(check_secrets(cfg, name, placeholder))
        if IPV6_TOKEN.search(cfg):
            findings.append(f"{name}: IPv6 config is forbidden in IPv4-only core")
        if f"<host-name>{name}</host-name>" not in cfg:
            findings.append(f"{name}: missing controller host-name")
        if f"<system-ip>{ctrl['system_ip']}</system-ip>" not in cfg:
            findings.append(f"{name}: missing controller system-ip")
        if "-20-12-" not in ctrl["image_definition"]:
            findings.append(f"{name}: controllers must run SD-WAN 20.12 to match the vEdges")

    return findings


def validate_all(root: Path = ROOT) -> list[str]:
    fabric = load_yaml(root / "data" / "fabric.yml")
    dmvpn = load_yaml(root / "data" / "dmvpn.yml")
    findings = link_findings(fabric)
    placeholder = dmvpn["psk_placeholder"]
    if placeholder in {"cisco", "cisco123", "admin"} or len(placeholder) < 8:
        findings.append("dmvpn: placeholder is too close to a real default")

    for device in fabric["devices"]:
        path = root / "rendered" / "nxos" / f"{device['hostname']}.cfg"
        if not path.exists():
            findings.append(f"{device['hostname']}: rendered NX-OS config missing")
            continue
        config = path.read_text()
        findings.extend(check_nxos(device, fabric, config))
        findings.extend(check_secrets(config, device["hostname"], placeholder))

    for device in [*dmvpn["hubs"], *dmvpn["spokes"]]:
        path = root / "rendered" / "iosxe" / f"{device['hostname']}.cfg"
        if not path.exists():
            findings.append(f"{device['hostname']}: rendered IOS-XE config missing")
            continue
        findings.extend(check_dmvpn(device, dmvpn, path.read_text()))

    enterprise = load_yaml(root / "data" / "enterprise_core.yml")
    findings.extend(check_enterprise(root, enterprise))
    return findings


def main() -> int:
    findings = validate_all()
    if findings:
        print(f"{len(findings)} problem(s):", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    fabric = load_yaml(ROOT / "data" / "fabric.yml")
    dmvpn = load_yaml(ROOT / "data" / "dmvpn.yml")
    enterprise = load_yaml(ROOT / "data" / "enterprise_core.yml")
    count = (
        len(fabric["devices"])
        + len(dmvpn["hubs"])
        + len(dmvpn["spokes"])
        + len(enterprise["sp_p_routers"])
        + len(enterprise["sp_pe_routers"])
        + len(enterprise["dc_routers"])
        + len(enterprise["dc_switches"])
        + 1
        + len(enterprise["sdwan_edges"])
        + len(enterprise["sdwan_controllers"])
    )
    print(f"ok: {count} devices match the source of truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
