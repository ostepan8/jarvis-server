#!/usr/bin/env python3
"""
System Performance Monitor for Scheduler Application

Monitors CPU, memory, disk, and network usage while the scheduler is running.
Useful for identifying resource bottlenecks during operation.
"""

import time
import json
import argparse
import psutil
from datetime import datetime
from typing import Dict, List
import threading
import signal
import sys

class SystemMonitor:
    def __init__(self, interval: int = 1):
        self.interval = interval
        self.monitoring = False
        self.data: List[Dict] = []
        self.start_time = None
        
    def collect_metrics(self) -> Dict:
        """Collect current system metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            # Network metrics
            network = psutil.net_io_counters()
            
            # Process-specific metrics (try to find scheduler processes)
            scheduler_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'cmdline']):
                try:
                    if any('scheduler' in str(item).lower() or 'api_server' in str(item).lower() 
                           for item in proc.info['cmdline'] or []):
                        scheduler_processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cpu_percent': proc.info['cpu_percent'],
                            'memory_mb': proc.info['memory_info'].rss / 1024 / 1024,
                            'cmdline': ' '.join(proc.info['cmdline'] or [])
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count,
                    'load_avg_1m': load_avg[0],
                    'load_avg_5m': load_avg[1],
                    'load_avg_15m': load_avg[2]
                },
                'memory': {
                    'total_gb': memory.total / 1024**3,
                    'available_gb': memory.available / 1024**3,
                    'used_gb': memory.used / 1024**3,
                    'percent': memory.percent,
                    'swap_used_gb': swap.used / 1024**3,
                    'swap_percent': swap.percent
                },
                'disk': {
                    'total_gb': disk.total / 1024**3,
                    'used_gb': disk.used / 1024**3,
                    'free_gb': disk.free / 1024**3,
                    'percent': disk.percent,
                    'read_bytes': disk_io.read_bytes if disk_io else 0,
                    'write_bytes': disk_io.write_bytes if disk_io else 0
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'scheduler_processes': scheduler_processes
            }
            
        except Exception as e:
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}
    
    def start_monitoring(self, duration: int = None):
        """Start monitoring system metrics."""
        self.monitoring = True
        self.start_time = time.time()
        self.data.clear()
        
        print(f"🔍 Starting system monitoring (interval: {self.interval}s)")
        if duration:
            print(f"📅 Monitoring duration: {duration} seconds")
        print("📊 Collecting CPU, Memory, Disk, Network, and Process metrics...")
        print("⏹️  Press Ctrl+C to stop monitoring")
        print()
        
        # Set up signal handler for graceful shutdown
        def signal_handler(sig, frame):
            print("\n🛑 Stopping monitoring...")
            self.monitoring = False
        
        signal.signal(signal.SIGINT, signal_handler)
        
        end_time = time.time() + duration if duration else float('inf')
        
        try:
            while self.monitoring and time.time() < end_time:
                metrics = self.collect_metrics()
                self.data.append(metrics)
                
                # Print live stats every 10 samples
                if len(self.data) % 10 == 0:
                    self.print_live_stats(metrics)
                
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        
        self.monitoring = False
        total_duration = time.time() - self.start_time
        print(f"\n✅ Monitoring complete. Collected {len(self.data)} samples over {total_duration:.1f} seconds")
    
    def print_live_stats(self, metrics: Dict):
        """Print live system statistics."""
        if 'error' in metrics:
            print(f"⚠️  Error: {metrics['error']}")
            return
        
        cpu = metrics['cpu']
        mem = metrics['memory']
        disk = metrics['disk']
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"CPU: {cpu['percent']:.1f}% | "
              f"Memory: {mem['percent']:.1f}% ({mem['used_gb']:.1f}GB) | "
              f"Disk: {disk['percent']:.1f}% | "
              f"Load: {cpu['load_avg_1m']:.2f}")
        
        # Show scheduler processes if found
        scheduler_procs = metrics.get('scheduler_processes', [])
        if scheduler_procs:
            for proc in scheduler_procs:
                print(f"    📱 {proc['name']} (PID {proc['pid']}): "
                      f"CPU {proc['cpu_percent']:.1f}%, Memory {proc['memory_mb']:.1f}MB")
    
    def analyze_data(self) -> Dict:
        """Analyze collected monitoring data."""
        if not self.data:
            return {'error': 'No data collected'}
        
        # Filter out error entries
        valid_data = [d for d in self.data if 'error' not in d]
        if not valid_data:
            return {'error': 'No valid data points'}
        
        # Extract metrics
        cpu_usage = [d['cpu']['percent'] for d in valid_data]
        memory_usage = [d['memory']['percent'] for d in valid_data]
        disk_usage = [d['disk']['percent'] for d in valid_data]
        load_avg = [d['cpu']['load_avg_1m'] for d in valid_data]
        
        # Calculate statistics
        def stats(values):
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'samples': len(values)
            }
        
        analysis = {
            'monitoring_duration': time.time() - self.start_time,
            'total_samples': len(valid_data),
            'cpu_stats': stats(cpu_usage),
            'memory_stats': stats(memory_usage),
            'disk_stats': stats(disk_usage),
            'load_avg_stats': stats(load_avg)
        }
        
        # Scheduler process analysis
        scheduler_cpu = []
        scheduler_memory = []
        for data_point in valid_data:
            for proc in data_point.get('scheduler_processes', []):
                scheduler_cpu.append(proc['cpu_percent'])
                scheduler_memory.append(proc['memory_mb'])
        
        if scheduler_cpu:
            analysis['scheduler_process_stats'] = {
                'cpu_stats': stats(scheduler_cpu),
                'memory_stats_mb': stats(scheduler_memory),
                'process_count': len(set(
                    proc['pid'] for data_point in valid_data 
                    for proc in data_point.get('scheduler_processes', [])
                ))
            }
        
        # Performance warnings
        warnings = []
        if analysis['cpu_stats']['avg'] > 80:
            warnings.append("High CPU usage detected (avg > 80%)")
        if analysis['memory_stats']['avg'] > 85:
            warnings.append("High memory usage detected (avg > 85%)")
        if analysis['load_avg_stats']['avg'] > psutil.cpu_count():
            warnings.append("High system load detected (avg > CPU count)")
        
        analysis['warnings'] = warnings
        
        return analysis
    
    def print_analysis(self, analysis: Dict):
        """Print analysis results."""
        if 'error' in analysis:
            print(f"❌ Analysis error: {analysis['error']}")
            return
        
        print("=" * 60)
        print("           SYSTEM PERFORMANCE ANALYSIS")
        print("=" * 60)
        print(f"Monitoring Duration: {analysis['monitoring_duration']:.1f} seconds")
        print(f"Total Samples:       {analysis['total_samples']}")
        print()
        
        # System metrics
        cpu = analysis['cpu_stats']
        mem = analysis['memory_stats']
        disk = analysis['disk_stats']
        load = analysis['load_avg_stats']
        
        print("SYSTEM METRICS")
        print("-" * 14)
        print(f"CPU Usage:     Min {cpu['min']:.1f}%  |  Avg {cpu['avg']:.1f}%  |  Max {cpu['max']:.1f}%")
        print(f"Memory Usage:  Min {mem['min']:.1f}%  |  Avg {mem['avg']:.1f}%  |  Max {mem['max']:.1f}%")
        print(f"Disk Usage:    Min {disk['min']:.1f}%  |  Avg {disk['avg']:.1f}%  |  Max {disk['max']:.1f}%")
        print(f"Load Average:  Min {load['min']:.2f}   |  Avg {load['avg']:.2f}   |  Max {load['max']:.2f}")
        print()
        
        # Scheduler process metrics
        if 'scheduler_process_stats' in analysis:
            sched = analysis['scheduler_process_stats']
            print("SCHEDULER PROCESS METRICS")
            print("-" * 25)
            print(f"Process Count:     {sched['process_count']}")
            cpu_s = sched['cpu_stats']
            mem_s = sched['memory_stats_mb']
            print(f"CPU Usage:     Min {cpu_s['min']:.1f}%  |  Avg {cpu_s['avg']:.1f}%  |  Max {cpu_s['max']:.1f}%")
            print(f"Memory Usage:  Min {mem_s['min']:.1f}MB |  Avg {mem_s['avg']:.1f}MB |  Max {mem_s['max']:.1f}MB")
            print()
        
        # Warnings
        warnings = analysis.get('warnings', [])
        if warnings:
            print("⚠️  PERFORMANCE WARNINGS")
            print("-" * 23)
            for warning in warnings:
                print(f"⚠️  {warning}")
            print()
        else:
            print("✅ No performance warnings detected")
            print()
        
        print("=" * 60)
    
    def save_data(self, filename: str):
        """Save monitoring data to JSON file."""
        with open(filename, 'w') as f:
            json.dump({
                'metadata': {
                    'start_time': self.start_time,
                    'interval': self.interval,
                    'total_samples': len(self.data)
                },
                'data': self.data
            }, f, indent=2)
        print(f"💾 Monitoring data saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description='System Performance Monitor')
    parser.add_argument('--interval', type=int, default=1,
                       help='Monitoring interval in seconds (default: 1)')
    parser.add_argument('--duration', type=int,
                       help='Monitoring duration in seconds (default: unlimited)')
    parser.add_argument('--save', help='Save data to JSON file')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress live output')
    
    args = parser.parse_args()
    
    # Check if psutil is available
    try:
        import psutil
    except ImportError:
        print("❌ Error: psutil is required for system monitoring")
        print("💡 Install with: pip3 install psutil")
        return
    
    monitor = SystemMonitor(args.interval)
    
    try:
        monitor.start_monitoring(args.duration)
        
        # Analyze results
        analysis = monitor.analyze_data()
        if not args.quiet:
            monitor.print_analysis(analysis)
        
        # Save data if requested
        if args.save:
            monitor.save_data(args.save)
        
    except KeyboardInterrupt:
        print("\n🛑 Monitoring interrupted")
        sys.exit(0)

if __name__ == '__main__':
    main()