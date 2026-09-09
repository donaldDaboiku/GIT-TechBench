"""Adapter inventory plus gateway ping, DNS, and internet reachability."""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app.core.config import load_app_config
from app.core.wmi_session import WmiSession
from app.models.diagnostic_result import DiagnosticResult, Status

logger = logging.getLogger("techbench.network")

MODULE = "Network"
CREATE_NO_WINDOW = 0x08000000


@dataclass
class AdapterReport:
    name: str
    ip: str
    mac: str
    gateway: str
    dns: list[str]
    is_up: bool | None


@dataclass
class PingResult:
    target: str
    ok: bool | None
    loss_percent: str
    latency_ms: str
    detail: str


@dataclass
class NetworkReport:
    adapters: list[AdapterReport]
    primary: AdapterReport | None
    gateway_ping: PingResult
    dns: PingResult
    internet: PingResult
    traffic: str
    status: Status
    message: str
    details: dict[str, str] = field(default_factory=dict)


class NetworkTester:
    phase = 2
    title = "Network Test"

    def __init__(self, internet_url: str | None = None, dns_hostname: str | None = None) -> None:
        cfg = load_app_config().get("network") or {}
        self.internet_url = internet_url or str(cfg.get("internet_check_url") or "")
        self.dns_hostname = dns_hostname or str(cfg.get("dns_test_hostname") or "")
        self.ping_count = int(cfg.get("ping_count") or 4)
        self.timeout = int(cfg.get("timeout_seconds") or 5)

    def check(self) -> tuple[NetworkReport, DiagnosticResult]:
        session = WmiSession()
        session.connect()
        try:
            adapters = _adapters(session)
        finally:
            session.close()
        primary = _primary(adapters)
        gateway_ip = primary.gateway if primary and primary.gateway != "Unavailable" else ""
        gateway_ping = ping_host(gateway_ip, self.ping_count) if gateway_ip else PingResult(
            target="",
            ok=None,
            loss_percent="Unavailable",
            latency_ms="Unavailable",
            detail="No gateway address measured.",
        )
        dns = resolve_hostname(self.dns_hostname, self.timeout)
        internet = http_check(self.internet_url, self.timeout)
        traffic = sample_traffic()

        gateway_ok = gateway_ping.ok is True
        dns_ok = dns.ok is True
        internet_ok = internet.ok is True
        details = {
            "gateway_ok": "true" if gateway_ok else "false" if gateway_ping.ok is False else "unknown",
            "dns_ok": "true" if dns_ok else "false" if dns.ok is False else "unknown",
            "internet_ok": "true" if internet_ok else "false" if internet.ok is False else "unknown",
        }

        if not adapters:
            status = Status.UNKNOWN
            message = "No network adapters enumerated."
        elif gateway_ping.ok is False and dns.ok is False:
            status = Status.FAIL
            message = "Gateway ping failed and DNS resolution failed."
        elif gateway_ping.ok is True and dns.ok is False:
            status = Status.WARNING
            message = "Gateway ping succeeded; DNS resolution failed."
        elif gateway_ping.ok is False:
            status = Status.WARNING
            message = "Gateway ping failed."
        elif internet.ok is False:
            status = Status.WARNING
            message = f"Local tests succeeded; internet check failed ({self.internet_url})."
        elif gateway_ping.ok is True and dns.ok is True and internet.ok is True:
            status = Status.PASS
            message = "Gateway, DNS, and internet checks succeeded."
        else:
            status = Status.UNKNOWN
            message = "Incomplete network results — some checks could not run."

        report = NetworkReport(
            adapters=adapters,
            primary=primary,
            gateway_ping=gateway_ping,
            dns=dns,
            internet=internet,
            traffic=traffic,
            status=status,
            message=message,
            details=details,
        )
        result = DiagnosticResult(
            module=MODULE,
            status=status,
            message=message,
            details=details,
        )
        return report, result


def ping_host(host: str, count: int = 4) -> PingResult:
    if not host:
        return PingResult(host, None, "Unavailable", "Unavailable", "No target.")
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    ping = os.path.join(system_root, "System32", "ping.exe")
    try:
        completed = subprocess.run(
            [ping, "-n", str(count), "-w", "1000", host],
            capture_output=True,
            text=True,
            timeout=count * 2 + 5,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PingResult(host, None, "Unavailable", "Unavailable", str(exc))
    text = completed.stdout or ""
    loss_m = re.search(r"Lost = \d+ \((\d+)% loss\)", text)
    avg_m = re.search(r"Average = (\d+)ms", text)
    loss = f"{loss_m.group(1)}%" if loss_m else "Unavailable"
    latency = f"{avg_m.group(1)} ms" if avg_m else "Unavailable"
    ok = completed.returncode == 0
    return PingResult(host, ok, loss, latency, text.strip()[-400:] or f"exit {completed.returncode}")


def resolve_hostname(hostname: str, timeout: int) -> PingResult:
    if not hostname:
        return PingResult("", None, "Unavailable", "Unavailable", "DNS test hostname is not configured.")
    socket.setdefaulttimeout(timeout)
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(hostname, None)
        elapsed = (time.perf_counter() - started) * 1000
        addrs = sorted({item[4][0] for item in infos})
        return PingResult(
            hostname,
            True,
            "0%",
            f"{elapsed:.0f} ms",
            "Resolved: " + ", ".join(addrs[:4]),
        )
    except OSError as exc:
        return PingResult(hostname, False, "Unavailable", "Unavailable", str(exc))


def http_check(url: str, timeout: int) -> PingResult:
    if not url:
        return PingResult("", None, "Unavailable", "Unavailable", "Internet check URL is not configured.")
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "GIT-TechBench/0.2"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0) or 0)
            elapsed = (time.perf_counter() - started) * 1000
            ok = 200 <= status < 400
            return PingResult(url, ok, "0%" if ok else "Unavailable", f"{elapsed:.0f} ms", f"HTTP {status}")
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        ok = 200 <= int(exc.code) < 400
        return PingResult(url, ok, "Unavailable", f"{elapsed:.0f} ms", f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return PingResult(url, False, "Unavailable", "Unavailable", str(exc))


def sample_traffic() -> str:
    try:
        import psutil

        first = psutil.net_io_counters()
        time.sleep(1.0)
        second = psutil.net_io_counters()
        down = max(0, second.bytes_recv - first.bytes_recv)
        up = max(0, second.bytes_sent - first.bytes_sent)
        return f"1s sample: down {down} B/s, up {up} B/s (adapter counters, not a speed test)"
    except Exception as exc:
        logger.exception("Traffic sample failed")
        return f"Unavailable ({exc})"


def _adapters(session: WmiSession) -> list[AdapterReport]:
    import psutil

    stats = {}
    try:
        stats = psutil.net_if_stats()
    except Exception:
        logger.exception("psutil.net_if_stats failed")

    adapters: list[AdapterReport] = []
    rows = session.query("Win32_NetworkAdapterConfiguration")
    for row in rows:
        ip_list = getattr(row, "IPAddress", None) or []
        ipv4 = next((ip for ip in ip_list if ":" not in str(ip)), "")
        if not ipv4:
            continue
        dns = [str(item) for item in (getattr(row, "DNSServerSearchOrder", None) or [])]
        gateways = [str(item) for item in (getattr(row, "DefaultIPGateway", None) or [])]
        name = _clean(getattr(row, "Description", None)) or "Adapter"
        mac = _clean(getattr(row, "MACAddress", None)) or "Unavailable"
        st = stats.get(name)
        adapters.append(
            AdapterReport(
                name=name,
                ip=str(ipv4),
                mac=mac,
                gateway=gateways[0] if gateways else "Unavailable",
                dns=dns,
                is_up=bool(st.isup) if st else None,
            )
        )
    if adapters:
        return adapters

    try:
        addrs = psutil.net_if_addrs()
        for name, addr_list in addrs.items():
            ipv4 = "Unavailable"
            mac = "Unavailable"
            for addr in addr_list:
                family = getattr(addr.family, "name", str(addr.family))
                if family in {"AF_INET", "2"} and addr.address and not addr.address.startswith("127."):
                    ipv4 = addr.address
                if "LINK" in family and addr.address:
                    mac = addr.address
            if ipv4 == "Unavailable":
                continue
            st = stats.get(name)
            adapters.append(
                AdapterReport(
                    name=name,
                    ip=ipv4,
                    mac=mac,
                    gateway="Unavailable",
                    dns=[],
                    is_up=bool(st.isup) if st else None,
                )
            )
    except Exception:
        logger.exception("psutil adapter fallback failed")
    return adapters


def _primary(adapters: list[AdapterReport]) -> AdapterReport | None:
    for item in adapters:
        if item.gateway != "Unavailable" and item.ip != "Unavailable":
            return item
    return adapters[0] if adapters else None


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""
