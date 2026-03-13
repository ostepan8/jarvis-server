"""Hardware monitoring service for the device running Jarvis.

Provides detailed system metrics: CPU (per-core), memory (with top consumers),
disk (per-partition), battery, thermals, network interfaces, uptime, and
process analysis.  Soft dependency on psutil — degrades gracefully without it.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# psutil.sensors_temperatures is platform-specific (Linux only).
# We guard calls with try/except, but Pyright flags it regardless.
# type: ignore[attr-defined] is applied at call site.


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Metric:
    """A single hardware measurement."""

    name: str
    value: Any
    unit: str = ""
    severity: Severity = Severity.OK
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceSnapshot:
    """Complete hardware snapshot of the host machine."""

    hostname: str = ""
    platform: str = ""
    uptime_seconds: float = 0.0
    cpu: List[Metric] = field(default_factory=list)
    memory: List[Metric] = field(default_factory=list)
    disk: List[Metric] = field(default_factory=list)
    battery: Optional[Metric] = None
    thermals: List[Metric] = field(default_factory=list)
    network: List[Metric] = field(default_factory=list)
    disk_io: List[Metric] = field(default_factory=list)
    network_io: List[Metric] = field(default_factory=list)
    memory_pressure: Optional[Dict[str, Any]] = None
    gpu: Optional[Metric] = None
    hardware_info: Optional[Dict[str, Any]] = None
    overall_severity: Severity = Severity.OK

    def to_dict(self) -> Dict[str, Any]:
        def _metric(m: Metric) -> Dict[str, Any]:
            return {
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "severity": m.severity.value,
                "details": m.details,
            }

        return {
            "hostname": self.hostname,
            "platform": self.platform,
            "uptime_seconds": self.uptime_seconds,
            "cpu": [_metric(m) for m in self.cpu],
            "memory": [_metric(m) for m in self.memory],
            "disk": [_metric(m) for m in self.disk],
            "battery": _metric(self.battery) if self.battery else None,
            "thermals": [_metric(m) for m in self.thermals],
            "network": [_metric(m) for m in self.network],
            "disk_io": [_metric(m) for m in self.disk_io],
            "network_io": [_metric(m) for m in self.network_io],
            "memory_pressure": self.memory_pressure,
            "gpu": _metric(self.gpu) if self.gpu else None,
            "hardware_info": self.hardware_info,
            "overall_severity": self.overall_severity.value,
        }


@dataclass
class ProcessInfo:
    """Lightweight snapshot of a running process."""

    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str = ""
    username: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": self.cpu_percent,
            "memory_mb": round(self.memory_mb, 1),
            "status": self.status,
            "username": self.username,
        }


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_CPU_WARN = 70.0
_CPU_CRIT = 90.0
_MEM_WARN = 80.0
_MEM_CRIT = 92.0
_DISK_WARN = 85.0
_DISK_CRIT = 95.0
_BATTERY_WARN = 20
_BATTERY_CRIT = 10
_TEMP_WARN = 80.0  # °C
_TEMP_CRIT = 95.0


def _severity(value: float, warn: float, crit: float) -> Severity:
    if value >= crit:
        return Severity.CRITICAL
    if value >= warn:
        return Severity.WARNING
    return Severity.OK


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DeviceMonitorService:
    """Collects hardware metrics from the host machine."""

    def __init__(self) -> None:
        self._psutil: Any = self._try_import_psutil()
        self._prev_disk_io: Any = None  # Previous disk_io_counters reading
        self._prev_disk_io_time: Optional[float] = None
        self._prev_net_io: Any = None  # Previous net_io_counters reading
        self._prev_net_io_time: Optional[float] = None
        self._cached_gpu_info: Optional[Metric] = None  # Cached at startup
        self._cached_hardware_info: Optional[Dict[str, Any]] = None  # Cached at startup

    @staticmethod
    def _try_import_psutil():
        try:
            import psutil
            return psutil
        except ImportError:
            return None

    @property
    def has_psutil(self) -> bool:
        return self._psutil is not None

    # -- Snapshot (quick) ---------------------------------------------------

    def snapshot(self) -> DeviceSnapshot:
        """Collect a full hardware snapshot.  Fast — no per-process enumeration."""
        snap = DeviceSnapshot(
            hostname=platform.node(),
            platform=f"{platform.system()} {platform.release()}",
        )

        psutil = self._psutil
        if psutil is None:
            snap.cpu.append(Metric("cpu", None, severity=Severity.WARNING,
                                   details={"error": "psutil not installed"}))
            return snap

        # Uptime
        snap.uptime_seconds = time.time() - psutil.boot_time()

        # CPU
        overall_cpu = psutil.cpu_percent(interval=0.1)
        snap.cpu.append(Metric(
            "cpu_overall", overall_cpu, unit="%",
            severity=_severity(overall_cpu, _CPU_WARN, _CPU_CRIT),
            details={"core_count": psutil.cpu_count(logical=True),
                     "physical_cores": psutil.cpu_count(logical=False)},
        ))
        per_core = psutil.cpu_percent(interval=0, percpu=True)
        for i, pct in enumerate(per_core):
            snap.cpu.append(Metric(
                f"core_{i}", pct, unit="%",
                severity=_severity(pct, _CPU_WARN, _CPU_CRIT),
            ))
        try:
            load1, load5, load15 = psutil.getloadavg()
            snap.cpu.append(Metric(
                "load_average", {"1m": load1, "5m": load5, "15m": load15},
            ))
        except (AttributeError, OSError):
            pass

        # Memory
        mem = psutil.virtual_memory()
        snap.memory.append(Metric(
            "ram", mem.percent, unit="%",
            severity=_severity(mem.percent, _MEM_WARN, _MEM_CRIT),
            details={
                "total_gb": round(mem.total / (1024 ** 3), 1),
                "available_gb": round(mem.available / (1024 ** 3), 1),
                "used_gb": round(mem.used / (1024 ** 3), 1),
            },
        ))
        try:
            swap = psutil.swap_memory()
            if swap.total > 0:
                snap.memory.append(Metric(
                    "swap", swap.percent, unit="%",
                    severity=_severity(swap.percent, _MEM_WARN, _MEM_CRIT),
                    details={"total_gb": round(swap.total / (1024 ** 3), 1),
                             "used_gb": round(swap.used / (1024 ** 3), 1)},
                ))
        except Exception:
            pass

        # Disk
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                snap.disk.append(Metric(
                    part.mountpoint, usage.percent, unit="%",
                    severity=_severity(usage.percent, _DISK_WARN, _DISK_CRIT),
                    details={
                        "total_gb": round(usage.total / (1024 ** 3), 1),
                        "used_gb": round(usage.used / (1024 ** 3), 1),
                        "free_gb": round(usage.free / (1024 ** 3), 1),
                        "fstype": part.fstype,
                    },
                ))
            except (PermissionError, OSError):
                continue

        # Battery
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                sev = Severity.OK
                if not batt.power_plugged:
                    sev = _severity(100 - batt.percent, 100 - _BATTERY_WARN, 100 - _BATTERY_CRIT)
                snap.battery = Metric(
                    "battery", batt.percent, unit="%",
                    severity=sev,
                    details={
                        "plugged_in": batt.power_plugged,
                        "secs_left": batt.secsleft if batt.secsleft > 0 else None,
                    },
                )
        except (AttributeError, Exception):
            pass

        # Thermals
        try:
            temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            if temps:
                for chip, entries in temps.items():
                    for entry in entries:
                        if entry.current > 0:
                            snap.thermals.append(Metric(
                                entry.label or chip, entry.current, unit="°C",
                                severity=_severity(entry.current, _TEMP_WARN, _TEMP_CRIT),
                                details={"high": entry.high, "critical": entry.critical},
                            ))
        except (AttributeError, Exception):
            pass

        # Network interfaces
        try:
            stats = psutil.net_if_stats()
            for iface, st in stats.items():
                if iface == "lo" or iface.startswith("lo"):
                    continue
                snap.network.append(Metric(
                    iface, "up" if st.isup else "down",
                    details={"speed_mbps": st.speed, "mtu": st.mtu},
                    severity=Severity.OK if st.isup else Severity.WARNING,
                ))
        except Exception:
            pass

        # Disk I/O rates
        snap.disk_io = self.get_disk_io_rates()

        # Network throughput
        snap.network_io = self.get_network_throughput()

        # Memory pressure (macOS)
        snap.memory_pressure = self.get_memory_pressure()

        # GPU info (cached)
        snap.gpu = self.get_gpu_info()

        # Hardware info (cached)
        snap.hardware_info = self.get_hardware_info()

        # Overall severity = worst across all metrics
        all_metrics = snap.cpu + snap.memory + snap.disk + snap.thermals + snap.network + snap.disk_io + snap.network_io
        if snap.battery:
            all_metrics.append(snap.battery)
        worst = Severity.OK
        for m in all_metrics:
            if m.severity == Severity.CRITICAL:
                worst = Severity.CRITICAL
                break
            if m.severity == Severity.WARNING:
                worst = Severity.WARNING
        snap.overall_severity = worst

        return snap

    # -- macOS-specific metrics ---------------------------------------------

    def get_disk_io_rates(self) -> List[Metric]:
        """Compute disk read/write bytes per second via delta between calls.

        First call returns an empty list (no prior reading to diff against).
        """
        psutil = self._psutil
        if psutil is None:
            return []
        try:
            counters = psutil.disk_io_counters(perdisk=False)
            if counters is None:
                return []
            now = time.time()
            prev = self._prev_disk_io
            prev_time = self._prev_disk_io_time
            self._prev_disk_io = counters
            self._prev_disk_io_time = now
            if prev is None or prev_time is None:
                return []
            dt = now - prev_time
            if dt <= 0:
                return []
            read_bps = (counters.read_bytes - prev.read_bytes) / dt
            write_bps = (counters.write_bytes - prev.write_bytes) / dt
            return [
                Metric("disk_read_bytes_sec", round(read_bps, 1), unit="B/s"),
                Metric("disk_write_bytes_sec", round(write_bps, 1), unit="B/s"),
            ]
        except Exception:
            return []

    def get_network_throughput(self) -> List[Metric]:
        """Compute network send/receive bytes per second via delta.

        First call returns an empty list (no prior reading to diff against).
        """
        psutil = self._psutil
        if psutil is None:
            return []
        try:
            counters = psutil.net_io_counters()
            if counters is None:
                return []
            now = time.time()
            prev = self._prev_net_io
            prev_time = self._prev_net_io_time
            self._prev_net_io = counters
            self._prev_net_io_time = now
            if prev is None or prev_time is None:
                return []
            dt = now - prev_time
            if dt <= 0:
                return []
            sent_bps = (counters.bytes_sent - prev.bytes_sent) / dt
            recv_bps = (counters.bytes_recv - prev.bytes_recv) / dt
            return [
                Metric("net_bytes_sent_sec", round(sent_bps, 1), unit="B/s"),
                Metric("net_bytes_recv_sec", round(recv_bps, 1), unit="B/s"),
            ]
        except Exception:
            return []

    def get_memory_pressure(self) -> Optional[Dict[str, Any]]:
        """Parse macOS ``vm_stat`` output for memory pressure details.

        Returns None on non-macOS systems or on failure.
        """
        if platform.system() != "Darwin":
            return None
        try:
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            data: Dict[str, Any] = {}
            for line in result.stdout.splitlines():
                match = re.match(r"^(.+?):\s+([\d]+)\.", line)
                if not match:
                    continue
                key_raw = match.group(1).strip().lower()
                value = int(match.group(2))
                if "pages active" in key_raw:
                    data["pages_active"] = value
                elif "pages inactive" in key_raw:
                    data["pages_inactive"] = value
                elif "pages wired" in key_raw:
                    data["pages_wired"] = value
                elif "pages occupied by compressor" in key_raw or "compressor" in key_raw:
                    data["pages_compressed"] = value
                elif "pageins" in key_raw:
                    data["pageins"] = value
                elif "pageouts" in key_raw:
                    data["pageouts"] = value
            return data if data else None
        except Exception:
            return None

    def get_battery_health(self) -> Optional[Dict[str, Any]]:
        """Query macOS ``ioreg`` for smart battery health data.

        Returns None on non-macOS or failure.
        """
        if platform.system() != "Darwin":
            return None
        try:
            result = subprocess.run(
                ["ioreg", "-r", "-c", "AppleSmartBattery", "-w0"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            data: Dict[str, Any] = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if '"CycleCount"' in line:
                    m = re.search(r"=\s*(\d+)", line)
                    if m:
                        data["cycle_count"] = int(m.group(1))
                elif '"MaxCapacity"' in line:
                    m = re.search(r"=\s*(\d+)", line)
                    if m:
                        data["max_capacity"] = int(m.group(1))
                elif '"DesignCapacity"' in line:
                    m = re.search(r"=\s*(\d+)", line)
                    if m:
                        data["design_capacity"] = int(m.group(1))
                elif '"Temperature"' in line:
                    m = re.search(r"=\s*(\d+)", line)
                    if m:
                        data["temperature_c"] = round(int(m.group(1)) / 100, 1)
            return data if data else None
        except Exception:
            return None

    def get_thermal_status(self) -> Optional[Dict[str, Any]]:
        """Query macOS thermal level and throttle status.

        Returns None on non-macOS or failure.
        """
        if platform.system() != "Darwin":
            return None
        data: Dict[str, Any] = {}
        try:
            result = subprocess.run(
                ["sysctl", "machdep.xcpm.cpu_thermal_level"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                m = re.search(r":\s*(\d+)", result.stdout)
                if m:
                    data["thermal_level"] = int(m.group(1))
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["pmset", "-g", "thermlog"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                data["thermlog"] = result.stdout.strip()
        except Exception:
            pass
        return data if data else None

    def get_gpu_info(self) -> Optional[Metric]:
        """Return GPU information from macOS ``system_profiler``.

        Caches the result — only runs the subprocess once.
        Returns None on non-macOS or failure.
        """
        if platform.system() != "Darwin":
            return None
        if self._cached_gpu_info is not None:
            return self._cached_gpu_info
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return None
            info = json.loads(result.stdout)
            displays = info.get("SPDisplaysDataType", [])
            if not displays:
                return None
            gpu = displays[0]
            details: Dict[str, Any] = {}
            if "sppci_model" in gpu:
                details["model"] = gpu["sppci_model"]
            if "spdisplays_vram" in gpu:
                details["vram"] = gpu["spdisplays_vram"]
            if "_spdisplays_vram" in gpu:
                details["vram"] = gpu["_spdisplays_vram"]
            if "sppci_vendor" in gpu:
                details["vendor"] = gpu["sppci_vendor"]
            if "spdisplays_vendor" in gpu:
                details["vendor"] = gpu["spdisplays_vendor"]
            model_name = details.get("model", "Unknown GPU")
            metric = Metric("gpu", model_name, details=details)
            self._cached_gpu_info = metric
            return metric
        except Exception:
            return None

    def get_hardware_info(self) -> Optional[Dict[str, Any]]:
        """Return hardware overview from macOS ``system_profiler``.

        Caches the result — only runs the subprocess once.
        Returns None on non-macOS or failure.
        """
        if platform.system() != "Darwin":
            return None
        if self._cached_hardware_info is not None:
            return self._cached_hardware_info
        try:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType", "-json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return None
            info = json.loads(result.stdout)
            hw_list = info.get("SPHardwareDataType", [])
            if not hw_list:
                return None
            hw = hw_list[0]
            data: Dict[str, Any] = {}
            if "chip_type" in hw:
                data["chip"] = hw["chip_type"]
            if "number_processors" in hw:
                data["core_count"] = hw["number_processors"]
            if "physical_memory" in hw:
                data["total_memory"] = hw["physical_memory"]
            if "machine_model" in hw:
                data["model"] = hw["machine_model"]
            if "machine_name" in hw:
                data["machine_name"] = hw["machine_name"]
            self._cached_hardware_info = data if data else None
            return self._cached_hardware_info
        except Exception:
            return None

    # -- Diagnostics (deeper) -----------------------------------------------

    def top_processes(self, by: str = "memory", limit: int = 10) -> List[ProcessInfo]:
        """Return the top N processes by CPU or memory usage."""
        psutil = self._psutil
        if psutil is None:
            return []
        procs: List[ProcessInfo] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status", "username"]):
            try:
                info = proc.info
                mem_mb = (info["memory_info"].rss / (1024 ** 2)) if info.get("memory_info") else 0.0
                procs.append(ProcessInfo(
                    pid=info["pid"],
                    name=info.get("name") or "unknown",
                    cpu_percent=info.get("cpu_percent") or 0.0,
                    memory_mb=mem_mb,
                    status=info.get("status") or "",
                    username=info.get("username") or "",
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        key = "memory_mb" if by == "memory" else "cpu_percent"
        procs.sort(key=lambda p: getattr(p, key), reverse=True)
        return procs[:limit]

    # -- Cleanup actions -----------------------------------------------------

    def clear_temp_files(self) -> Dict[str, Any]:
        """Remove files from the system temp directory older than 24 hours.

        Returns a summary of what was cleared.
        """
        tmp = Path(tempfile.gettempdir())
        cleared = 0
        freed_bytes = 0
        errors = 0
        cutoff = time.time() - 86400  # 24h ago

        for entry in tmp.iterdir():
            try:
                stat = entry.stat()
                if stat.st_mtime < cutoff:
                    size = stat.st_size
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink(missing_ok=True)
                    cleared += 1
                    freed_bytes += size
            except (PermissionError, OSError):
                errors += 1

        return {
            "cleared": cleared,
            "freed_mb": round(freed_bytes / (1024 ** 2), 1),
            "errors": errors,
            "tmp_dir": str(tmp),
        }

    def get_zombie_processes(self) -> List[ProcessInfo]:
        """Find zombie or unresponsive processes."""
        psutil = self._psutil
        if psutil is None:
            return []
        zombies: List[ProcessInfo] = []
        for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info", "username"]):
            try:
                info = proc.info
                if info.get("status") in ("zombie", "stopped"):
                    mem_mb = (info["memory_info"].rss / (1024 ** 2)) if info.get("memory_info") else 0.0
                    zombies.append(ProcessInfo(
                        pid=info["pid"],
                        name=info.get("name") or "unknown",
                        cpu_percent=info.get("cpu_percent") or 0.0,
                        memory_mb=mem_mb,
                        status=info.get("status") or "",
                        username=info.get("username") or "",
                    ))
            except Exception:
                continue
        return zombies

    def kill_process(self, pid: int) -> Dict[str, Any]:
        """Attempt to terminate a process by PID (SIGTERM, then SIGKILL)."""
        psutil = self._psutil
        if psutil is None:
            return {"success": False, "error": "psutil not installed"}
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            return {"success": True, "pid": pid, "name": name, "action": "terminated"}
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"Process {pid} not found"}
        except psutil.AccessDenied:
            return {"success": False, "error": f"Permission denied for PID {pid}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # -- Formatting helpers --------------------------------------------------

    @staticmethod
    def format_uptime(seconds: float) -> str:
        """Human-readable uptime string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
