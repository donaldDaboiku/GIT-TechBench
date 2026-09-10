"""Central diagnostic runner for automated checks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from app.core.health_checker import overall_status
from app.core.recommendation_engine import RecommendationEngine
from app.models.diagnostic_result import DiagnosticResult, Status
from app.modules.battery.battery_checker import BatteryChecker
from app.modules.cpu.cpu_monitor import CpuMonitor
from app.modules.gpu.gpu_monitor import GpuMonitor
from app.modules.memory.ram_checker import RamChecker
from app.modules.network.network_tester import NetworkTester
from app.modules.storage.disk_checker import DiskChecker

ProgressFn = Callable[[str], None]
ResultFn = Callable[[DiagnosticResult], None]

AUTOMATED_MODULES = ("Battery", "Storage", "Memory", "CPU", "GPU", "Network")
INTERACTIVE_MODULES = ("Keyboard", "Mouse", "Display", "Audio", "Camera", "Windows")


class DiagnosticsEngine:
    """Runs selected checks and returns structured session results."""

    def __init__(self) -> None:
        self.recommender = RecommendationEngine()

    def run_automated(
        self,
        *,
        progress: ProgressFn | None = None,
        on_result: ResultFn | None = None,
        internet_url: str | None = None,
        dns_hostname: str | None = None,
    ) -> list[DiagnosticResult]:
        """Non-destructive checks that do not need a technician at the keyboard."""
        results: list[DiagnosticResult] = []

        def emit(label: str, result: DiagnosticResult) -> None:
            annotated = self.recommender.annotate(result)
            results.append(annotated)
            if on_result:
                on_result(annotated)
            if progress:
                progress(f"{label}: {annotated.status.value} — {annotated.message}")

        if progress:
            progress("Battery health…")
        _report, battery = BatteryChecker().check()
        emit("Battery", battery)

        if progress:
            progress("Storage health…")
        _s, storage = DiskChecker().check()
        emit("Storage", storage)

        if progress:
            progress("Memory inventory…")
        _m, memory = RamChecker().check()
        emit("Memory", memory)

        if progress:
            progress("CPU snapshot…")
        _c, cpu = CpuMonitor().snapshot(0.8)
        emit("CPU", cpu)

        if progress:
            progress("GPU inventory…")
        _g, gpu = GpuMonitor().snapshot()
        emit("GPU", gpu)

        if progress:
            progress("Network tests…")
        _n, network = NetworkTester(internet_url=internet_url, dns_hostname=dns_hostname).check()
        emit("Network", network)
        return results

    def merge_session(
        self,
        automated: list[DiagnosticResult],
        interactive: dict[str, DiagnosticResult],
    ) -> list[DiagnosticResult]:
        merged = list(automated)
        for name in INTERACTIVE_MODULES:
            if name in interactive:
                merged.append(self.recommender.annotate(interactive[name]))
            else:
                merged.append(
                    DiagnosticResult(
                        module=name,
                        status=Status.UNKNOWN,
                        message="Not run this session (interactive test).",
                    )
                )
        return merged

    def build_session(
        self,
        device_name: str,
        tests: list[DiagnosticResult],
        diagnostic_date: date | None = None,
    ) -> dict[str, object]:
        when = diagnostic_date or date.today()
        return {
            "device_name": device_name,
            "diagnostic_date": when.isoformat(),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "overall_status": overall_status(tests).value,
            "tests": [
                {
                    "module": item.module,
                    "status": item.status.value,
                    "message": item.message,
                    "likely_cause": item.likely_cause,
                    "recommended_action": item.recommended_action,
                    "confidence": item.confidence.value if item.confidence else "",
                }
                for item in tests
            ],
        }

    def empty_session(self, device_name: str) -> dict[str, object]:
        return self.build_session(device_name, [])
