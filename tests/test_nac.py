from pathlib import Path

import pytest

from nac.collect import collect_running_config
from nac.validate import ROOT, check_dmvpn, check_secrets, load_yaml, validate_all

DMVPN = load_yaml(ROOT / "data" / "dmvpn.yml")
SPOKE = DMVPN["spokes"][0]


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
    assert nxos == {device["hostname"] for device in fabric["devices"]}
    assert ios == {device["hostname"] for device in DMVPN["hubs"] + DMVPN["spokes"]}
    assert not list(Path(ROOT / "rendered").rglob("*password*"))
