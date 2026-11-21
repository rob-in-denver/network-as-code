from pathlib import Path

import pytest

from nac.collect import collect_running_config
from nac.validate import ROOT, check_dmvpn, check_enterprise, check_secrets, load_yaml, validate_all

DMVPN = load_yaml(ROOT / "data" / "dmvpn.yml")
SPOKE = DMVPN["spokes"][0]
ENTERPRISE = load_yaml(ROOT / "data" / "enterprise_core.yml")


def test_source_of_truth_matches_rendered_configs():
    findings = validate_all(ROOT)
    assert findings == []


def test_secret_scan_rejects_a_password_line():
    findings = check_secrets("username admin password cisco123", "lab", DMVPN["psk_placeholder"])
    assert findings


def test_secret_scan_rejects_a_real_pre_shared_key():
    findings = check_secrets("pre-shared-key not-the-placeholder", "lab", DMVPN["psk_placeholder"])
    assert any("placeholder" in item for item in findings)


def test_spoke_must_install_nhrp_shortcut():
    config = (ROOT / "rendered" / "iosxe" / f"{SPOKE['hostname']}.cfg").read_text()
    broken = config.replace("ip nhrp shortcut", "! shortcut removed")
    findings = check_dmvpn(SPOKE, DMVPN, broken)
    assert any("ip nhrp shortcut" in item for item in findings)


def test_live_collection_does_not_run_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NETMIKO_USERNAME", raising=False)
    monkeypatch.delenv("NETMIKO_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="NETMIKO_USERNAME"):
        collect_running_config("192.0.2.1")


def test_rendered_tree_covers_every_device():
    fabric = load_yaml(ROOT / "data" / "fabric.yml")
    nxos = {path.stem for path in (ROOT / "rendered" / "nxos").glob("*.cfg")}
    ios = {path.stem for path in (ROOT / "rendered" / "iosxe").glob("*.cfg")}
    iosxr = {path.stem for path in (ROOT / "rendered" / "iosxr").glob("*.cfg")}
    enterprise = {path.stem for path in (ROOT / "rendered" / "enterprise").glob("*.cfg")}
    sdwan_edges = {path.stem for path in (ROOT / "rendered" / "sdwan").glob("*.cfg")}
    sdwan_ctrls = {path.stem for path in (ROOT / "rendered" / "sdwan").glob("*.yaml")}

    assert nxos == {device["hostname"] for device in fabric["devices"]}
    assert ios == {device["hostname"] for device in DMVPN["hubs"] + DMVPN["spokes"]}
    assert iosxr == {device["hostname"] for device in ENTERPRISE["sp_p_routers"]}
    assert enterprise == {
        device["hostname"]
        for device in ENTERPRISE["sp_pe_routers"] + ENTERPRISE["dc_routers"] + ENTERPRISE["dc_switches"]
    } | {ENTERPRISE["isp"]["hostname"]}
    assert sdwan_edges == {device["hostname"] for device in ENTERPRISE["sdwan_edges"]}
    assert sdwan_ctrls == {device["hostname"] for device in ENTERPRISE["sdwan_controllers"]}
    assert not list(Path(ROOT / "rendered").rglob("*password*"))


def test_enterprise_core_is_ipv4_only_and_dc_hub_terminates_dmvpn():
    assert ENTERPRISE["ipv4_only"] is True
    assert check_enterprise(ROOT, ENTERPRISE) == []
    dc_r1 = (ROOT / "rendered" / "enterprise" / "DC-R1.cfg").read_text()
    assert "ip nhrp redirect" in dc_r1
    assert "tunnel vrf INET" in dc_r1


def test_two_dc_routers_face_the_single_isp_and_edges_are_vedge_20_12():
    isp = (ROOT / "rendered" / "enterprise" / "ISP.cfg").read_text()
    assert "router " not in isp
    assert "172.16.0.249 255.255.255.252" in isp and "172.16.0.245 255.255.255.252" in isp
    dc_r1 = (ROOT / "rendered" / "enterprise" / "DC-R1.cfg").read_text()
    dc_r4 = (ROOT / "rendered" / "enterprise" / "DC-R4.cfg").read_text()
    assert "ip route vrf INET 0.0.0.0 0.0.0.0 172.16.0.249" in dc_r1
    assert "ip route 0.0.0.0 0.0.0.0 172.16.0.245 name ISP-INTERNET" in dc_r4
    for name in ("DC-R2", "DC-R3"):
        cfg = (ROOT / "rendered" / "enterprise" / f"{name}.cfg").read_text()
        assert "172.16.0." not in cfg
    for edge in ENTERPRISE["sdwan_edges"]:
        assert edge["node_definition"] == "cat-sdwan-vedge"
        assert edge["image_definition"] == "vedge_20.12.8"
    for ctrl in ENTERPRISE["sdwan_controllers"]:
        assert ctrl["image_definition"].endswith("-20-12-8-1")


def test_vedge_check_flags_a_missing_vpn512():
    edge = ENTERPRISE["sdwan_edges"][0]
    path = ROOT / "rendered" / "sdwan" / f"{edge['hostname']}.cfg"
    original = path.read_text()
    try:
        path.write_text(original.replace("<vpn-id>512</vpn-id>", "<vpn-id>9999</vpn-id>"))
        assert any("vpn-id>512" in item for item in check_enterprise(ROOT, ENTERPRISE))
    finally:
        path.write_text(original)
