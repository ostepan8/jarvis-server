# DeviceMonitorAgent

**Class**: `DeviceMonitorAgent`
**Module**: `jarvis/agents/device_monitor_agent/__init__.py`
**Feature Flag**: `enable_device_monitor`

## Capabilities

### device_status
Current snapshot of host hardware metrics.
- "How's my computer doing?"
- "System status"
- "Check CPU and memory usage"
- "Is the disk almost full?"

### device_diagnostics
Deep dive into resource usage — top processes, resource hogs.
- "What's eating all my RAM?"
- "Show top processes"
- "Why is my computer slow?"
- "What's hogging the CPU?"

### device_cleanup
Clean temporary files and free disk space.
- "Clean up temp files"
- "Free up disk space"
- "Delete temporary files"

### device_history
Metric trends over time using stored time-series data.
- "Has CPU been high all day?"
- "Show memory trends"
- "Temperature history"
- "System performance over time"

## Background Monitoring
- Probes every 30 seconds (configurable: `device_monitor_probe_interval`)
- Metrics stored in `MetricsStore` (time-series)
- Alerts broadcast when thresholds exceeded

## Architecture
- `DeviceMonitorService` collects OS-level metrics (psutil-based)
- `MetricsStore` provides time-series storage and trend queries
- Integrated with HealthAgent for system-wide health picture
