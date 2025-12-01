import os
import time
import psutil
import threading
import csv
from pathlib import Path
from datetime import datetime

class performance_measure:
    def __init__(self, monitor_interval=None):
        """
        Initialize performance measurement.

        Args:
            monitor_interval: If None, use snapshot mode (for short processes).
                            If float (e.g., 1.0), use continuous monitoring with
                            sampling every N seconds (for long processes).
        """
        self.proc = psutil.Process(os.getpid())
        self.ncpu = psutil.cpu_count(logical=True) or 1
        self._state = {}

        # Continuous monitoring setup
        self.monitor_interval = monitor_interval
        self._monitoring = False
        self._monitor_thread = None
        self._samples = []

    def start(self):
        now = datetime.now()
        formatted = now.strftime("%Y-%m-%d %H:%M:%S")
        self._state["dt"] = formatted
        self._state["t0"] = time.perf_counter()

        # Process-level snapshots
        self._state["cpu_proc_before"] = self.proc.cpu_times()
        mi = self.proc.memory_info()
        self._state["rss_before"] = mi.rss
        self._state["vms_before"] = getattr(mi, "vms", 0)

        # System-wide snapshots
        self._state["cpu_sys_before"] = psutil.cpu_times()
        self._state["vmem_before"] = psutil.virtual_memory()
        self._state["swap_before"] = psutil.swap_memory()
        self._state["disk_before"] = psutil.disk_io_counters()
        self._state["net_before"] = psutil.net_io_counters()

        # Start continuous monitoring if enabled
        if self.monitor_interval is not None:
            self._start_monitoring()

    def _start_monitoring(self):
        """Start background thread for continuous monitoring."""
        self._monitoring = True
        self._samples = []
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _monitor_loop(self):
        """Background monitoring loop that samples metrics periodically."""
        start_time = time.perf_counter()

        while self._monitoring:
            try:
                # Sample process metrics
                cpu_times = self.proc.cpu_times()
                mem_info = self.proc.memory_info()

                # Sample system metrics
                sys_cpu_times = psutil.cpu_times()
                sys_vmem = psutil.virtual_memory()

                sample = {
                    'timestamp': time.perf_counter() - start_time,

                    # Process metrics
                    'cpu_user': cpu_times.user,
                    'cpu_system': cpu_times.system,
                    'rss_mib': mem_info.rss / 1024**2,
                    'vms_mib': getattr(mem_info, 'vms', 0) / 1024**2,

                    # System metrics
                    'sys_cpu_user': sys_cpu_times.user,
                    'sys_cpu_system': getattr(sys_cpu_times, 'system', 0),
                    'sys_cpu_idle': sys_cpu_times.idle,
                    'sys_cpu_iowait': getattr(sys_cpu_times, 'iowait', 0),
                    'sys_ram_used_mib': sys_vmem.used / 1024**2,
                    'sys_ram_available_mib': sys_vmem.available / 1024**2,
                    'sys_ram_percent': sys_vmem.percent,
                }

                # Get instantaneous CPU percent (non-blocking)
                try:
                    sample['cpu_percent'] = self.proc.cpu_percent(interval=None)
                except:
                    sample['cpu_percent'] = 0.0

                self._samples.append(sample)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break

            time.sleep(self.monitor_interval)

    def _stop_monitoring(self):
        """Stop background monitoring thread."""
        if self._monitoring:
            self._monitoring = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=2.0)

    def end(self, func, *args, **kwargs):
        """
        Run `func(*args, **kwargs)` and take snapshots AFTER.
        """
        result = func(*args, **kwargs)

        self._state["t1"] = time.perf_counter()

        # Stop monitoring before taking final snapshots
        self._stop_monitoring()

        # Process after
        cpu_proc_after = self.proc.cpu_times()
        mi_after = self.proc.memory_info()

        self._state["cpu_proc_after"] = cpu_proc_after
        self._state["rss_after"] = mi_after.rss
        self._state["vms_after"] = getattr(mi_after, "vms", 0)

        # System after
        self._state["cpu_sys_after"] = psutil.cpu_times()
        self._state["vmem_after"] = psutil.virtual_memory()
        self._state["swap_after"] = psutil.swap_memory()
        self._state["disk_after"] = psutil.disk_io_counters()
        self._state["net_after"] = psutil.net_io_counters()

        return result

    def measure(self):
        s = self._state
        # --- Time ---
        dt = s['dt']
        wall = s["t1"] - s["t0"]

        # --- Process CPU (normalized by cores, 0–100%) ---
        cpu_before = s["cpu_proc_before"]
        cpu_after = s["cpu_proc_after"]
        cpu_proc_used = (
            (cpu_after.user - cpu_before.user) +
            (cpu_after.system - cpu_before.system) +
            (getattr(cpu_after, 'children_user', 0) - getattr(cpu_before, 'children_user', 0)) +
            (getattr(cpu_after, 'children_system', 0) - getattr(cpu_before, 'children_system', 0))
        )
        cpu_proc_pct = (cpu_proc_used / wall) * 100 / self.ncpu if wall > 0 else 0.0

        # --- System CPU (0–100%) ---
        sys_before = s["cpu_sys_before"]
        sys_after = s["cpu_sys_after"]

        def delta(field):
            return getattr(sys_after, field, 0.0) - getattr(sys_before, field, 0.0)

        idle_delta = delta("idle")
        busy_delta = 0.0
        for name in sys_before._fields:
            if name not in ("idle", "iowait"):  # Exclude idle and iowait
                busy_delta += delta(name)

        total_delta = busy_delta + idle_delta + delta("iowait")
        cpu_sys_pct = (busy_delta / total_delta * 100.0) if total_delta > 0 else 0.0

        # --- Process memory ---
        rss_before_mib = s["rss_before"] / 1024**2
        rss_after_mib = s["rss_after"] / 1024**2
        rss_delta_mib = rss_after_mib - rss_before_mib

        vms_before_mib = s["vms_before"] / 1024**2
        vms_after_mib = s["vms_after"] / 1024**2
        vms_delta_mib = vms_after_mib - vms_before_mib

        # --- System memory ---
        vm_after = s["vmem_after"]

        result = {
            "dt": dt,
            "time_s": wall,
        }

        # Add continuous monitoring stats if available
        if self._samples:
            result["Continuous"] = self._compute_monitoring_stats()

        result["Snapshot"] = {
                 "cpu_proc_pct": cpu_proc_pct,
                 "rss_before_mib": rss_before_mib,
                 "rss_after_mib": rss_after_mib,
                 "rss_delta_mib": rss_delta_mib,
                 "vms_before_mib": vms_before_mib,
                 "vms_after_mib": vms_after_mib,
                 "vms_delta_mib": vms_delta_mib,
                 "cpu_sys_pct": cpu_sys_pct,
                 "ram_total_mib": vm_after.total / 1024**2,
                 "ram_used_mib": vm_after.used / 1024**2,
                 "ram_available_mib": vm_after.available / 1024**2,
                 "ram_used_pct": vm_after.percent,
             }

        return result

    def _compute_monitoring_stats(self):
        """Compute statistics from continuous monitoring samples."""
        if not self._samples:
            return None
        rss_values = [s['rss_mib'] for s in self._samples]
        vms_values = [s['vms_mib'] for s in self._samples]
        cpu_values = [s['cpu_percent'] for s in self._samples]

        # System metrics
        sys_ram_used = [s['sys_ram_used_mib'] for s in self._samples]
        sys_ram_available = [s['sys_ram_available_mib'] for s in self._samples]
        sys_ram_percent = [s['sys_ram_percent'] for s in self._samples]

        # Compute process CPU usage between samples
        cpu_usage_samples = []
        for i in range(1, len(self._samples)):
            prev = self._samples[i-1]
            curr = self._samples[i]
            time_delta = curr['timestamp'] - prev['timestamp']
            if time_delta > 0:
                cpu_delta = (
                    (curr['cpu_user'] - prev['cpu_user']) +
                    (curr['cpu_system'] - prev['cpu_system'])
                )
                cpu_pct = (cpu_delta / time_delta) * 100 / self.ncpu
                cpu_usage_samples.append(cpu_pct)

        # Compute system CPU usage between samples
        sys_cpu_usage_samples = []
        for i in range(1, len(self._samples)):
            prev = self._samples[i-1]
            curr = self._samples[i]

            # Calculate busy and idle deltas
            busy_delta = 0
            for field in ['sys_cpu_user', 'sys_cpu_system']:
                busy_delta += curr.get(field, 0) - prev.get(field, 0)

            idle_delta = curr['sys_cpu_idle'] - prev['sys_cpu_idle']
            iowait_delta = curr.get('sys_cpu_iowait', 0) - prev.get('sys_cpu_iowait', 0)

            total_delta = busy_delta + idle_delta + iowait_delta

            if total_delta > 0:
                sys_cpu_pct = (busy_delta / total_delta) * 100
                sys_cpu_usage_samples.append(sys_cpu_pct)

        stats = {
            "sample_count": len(self._samples),
            "sample_interval_s": self.monitor_interval,

            # Process memory stats
            "rss_peak_mib": max(rss_values),
            "rss_min_mib": min(rss_values),
            "rss_mean_mib": sum(rss_values) / len(rss_values),
            "rss_final_mib": rss_values[-1],

            "vms_peak_mib": max(vms_values),
            "vms_min_mib": min(vms_values),
            "vms_mean_mib": sum(vms_values) / len(vms_values),

            # Process CPU stats
            "cpu_mean_pct": sum(cpu_usage_samples) / len(cpu_usage_samples) if cpu_usage_samples else 0,
            "cpu_max_pct": max(cpu_usage_samples) if cpu_usage_samples else 0,
            "cpu_min_pct": min(cpu_usage_samples) if cpu_usage_samples else 0,

            # System CPU stats
            "sys_cpu_mean_pct": sum(sys_cpu_usage_samples) / len(sys_cpu_usage_samples) if sys_cpu_usage_samples else 0,
            "sys_cpu_max_pct": max(sys_cpu_usage_samples) if sys_cpu_usage_samples else 0,
            "sys_cpu_min_pct": min(sys_cpu_usage_samples) if sys_cpu_usage_samples else 0,

            # System memory stats
            "sys_ram_used_peak_mib": max(sys_ram_used),
            "sys_ram_used_min_mib": min(sys_ram_used),
            "sys_ram_used_mean_mib": sum(sys_ram_used) / len(sys_ram_used),
            "sys_ram_available_mean_mib": sum(sys_ram_available) / len(sys_ram_available),
            "sys_ram_percent_mean": sum(sys_ram_percent) / len(sys_ram_percent),
            "sys_ram_percent_max": max(sys_ram_percent),

            # Raw samples for plotting
            #"samples": self._samples,
        }

        return stats

    def get_samples(self):
        """Get raw monitoring samples for custom analysis or plotting."""
        return self._samples.copy() if self._samples else []

    def print_summary(self):
        """Print a formatted summary of measurements."""
        metrics = self.measure()

        print(f"\n{'='*60}")
        print(f"Performance Measurement Summary")
        print(f"{'='*60}")
        print(f"Timestamp: {metrics['dt']}")
        print(f"Duration:  {metrics['time_s']:.2f} seconds")
        print(f"\n--- Process Metrics ---")
        print(f"CPU Usage:        {metrics['process']['cpu_pct']:.2f}%")
        print(f"RSS Memory:       {metrics['process']['rss_after_mib']:.2f} MB")
        print(f"RSS Delta:        {metrics['process']['rss_delta_mib']:+.2f} MB")

        if 'Continuous' in metrics:
            mon = metrics['Continuous']
            print(f"\n--- Continuous Monitoring ({mon['sample_count']} samples) ---")
            print(f"Process RSS Peak: {mon['rss_peak_mib']:.2f} MB")
            print(f"Process RSS Mean: {mon['rss_mean_mib']:.2f} MB")
            print(f"Process RSS Min:  {mon['rss_min_mib']:.2f} MB")
            print(f"Process CPU Mean: {mon['cpu_mean_pct']:.2f}%")
            print(f"Process CPU Max:  {mon['cpu_max_pct']:.2f}%")
            print(f"Process CPU Min:  {mon['cpu_min_pct']:.2f}%")
            print(f"\nSystem CPU Mean:  {mon['sys_cpu_mean_pct']:.2f}%")
            print(f"System CPU Max:   {mon['sys_cpu_max_pct']:.2f}%")
            print(f"System CPU Min:   {mon['sys_cpu_min_pct']:.2f}%")
            print(f"System RAM Mean:  {mon['sys_ram_used_mean_mib']:.2f} MB ({mon['sys_ram_percent_mean']:.1f}%)")
            print(f"System RAM Peak:  {mon['sys_ram_used_peak_mib']:.2f} MB ({mon['sys_ram_percent_max']:.1f}%)")

        print(f"\n--- System Metrics ---")
        print(f"System CPU:       {metrics['system']['cpu_pct']:.2f}%")
        print(f"System RAM:       {metrics['system']['ram_used_mib']:.2f} / "
              f"{metrics['system']['ram_total_mib']:.2f} MB "
              f"({metrics['system']['ram_used_pct']:.1f}%)")
        print(f"{'='*60}\n")


def stringify_report(metrics):
    lines = []
    lines.append(f"Time: {metrics['time_s']:.4f} s")
    lines.append("Snapshot:")
    for k, v in metrics["Snapshot"].items():
        lines.append(f"  {k}: {v}")
    lines.append("Continuous:")
    for k, v in metrics["Continuous"].items():
       lines.append(f"  {k}: {v}")
    return "\n".join(lines)



def metrics_to_csv(metrics: dict, path: str, process_name: str, size_bytes: int = 0):
    """
    Writes profiler output to CSV.
    Automatically creates the file and the header on first write.
    Accepts the full metrics dict from ProfilerBoth.measure().
    """

    # Ensure the directory exists
    csv_path = Path(path).expanduser().resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Flatten nested dict structure for CSV
    flat = {}
    flat["process"] = process_name
    flat["size_bytes"] = size_bytes
    for key, value in metrics.items():
        if isinstance(value, dict):
            for k2, v2 in value.items():
                flat[f"{key}_{k2}"] = v2
        else:
            flat[key] = value

    # Write CSV
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat.keys()))

        if not file_exists:
            writer.writeheader()

        writer.writerow(flat)
