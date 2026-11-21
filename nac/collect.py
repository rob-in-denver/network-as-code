"""Optional live collection.

CI does not import Netmiko and does not call this module. Credentials come from
the environment, never from argv or from the repository.
"""

from __future__ import annotations

import os


def collect_running_config(host: str) -> str:
    username = os.environ.get("NETMIKO_USERNAME")
    password = os.environ.get("NETMIKO_PASSWORD")
    device_type = os.environ.get("NETMIKO_DEVICE_TYPE", "cisco_ios")
    if not username or not password:
        raise RuntimeError("Set NETMIKO_USERNAME and NETMIKO_PASSWORD to collect a live config")
    try:
        from netmiko import ConnectHandler
    except ImportError as exc:
        raise RuntimeError("netmiko is not installed") from exc
    with ConnectHandler(
        device_type=device_type,
        host=host,
        username=username,
        password=password,
    ) as connection:
        return str(connection.send_command("show running-config"))
