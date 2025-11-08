#!/usr/bin/env python3
"""
Performance Metrics Dashboard for Scheduler System

This script analyzes benchmark results from the C++ performance suite
and generates comprehensive performance reports and visualizations.
"""

import os
import json
import csv
import argparse
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sqlite3

class PerformanceAnalyzer:
    def __init__(self, results_dir: str = "benchmark_results"):
        self.results_dir = Path(results_dir)
        self.metrics = {}
        
    def load_csv_results(self) -> Dict[str, Any]:
        """Load all CSV benchmark results from the results directory."""
        results = {}
        
        if not self.results_dir.exists():
            print(f"Results directory {self.results_dir} not found.")
            return results
            
        for csv_file in self.results_dir.glob("*.csv"):
            benchmark_name = csv_file.stem.replace("_results", "")
            results[benchmark_name] = self._parse_csv_file(csv_file)
            
        return results
    
    def _parse_csv_file(self, csv_file: Path) -> Dict[str, float]:
        """Parse a single CSV results file."""
        metrics = {}
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metrics[row['metric']] = float(row['value'])
        except Exception as e:
            print(f"Error parsing {csv_file}: {e}")
        return metrics
    
    def analyze_performance_trends(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance trends across different benchmarks."""
        analysis = {
            'summary': {},
            'bottlenecks': [],
            'recommendations': []
        }
        
        # Extract key metrics
        throughput_metrics = []
        latency_metrics = []
        memory_metrics = []
        
        for benchmark, metrics in results.items():
            if 'throughput_ops_per_sec' in metrics:
                throughput_metrics.append({
                    'benchmark': benchmark,
                    'throughput': metrics['throughput_ops_per_sec']
                })
            
            if 'mean_time_ms' in metrics:
                latency_metrics.append({
                    'benchmark': benchmark,
                    'latency': metrics['mean_time_ms']
                })
            
            if 'peak_memory_mb' in metrics and metrics['peak_memory_mb'] > 0:
                memory_metrics.append({
                    'benchmark': benchmark,
                    'memory': metrics['peak_memory_mb']
                })
        
        # Summary statistics
        if throughput_metrics:
            throughputs = [m['throughput'] for m in throughput_metrics]
            analysis['summary']['avg_throughput'] = statistics.mean(throughputs)
            analysis['summary']['min_throughput'] = min(throughputs)
            analysis['summary']['max_throughput'] = max(throughputs)
        
        if latency_metrics:
            latencies = [m['latency'] for m in latency_metrics]
            analysis['summary']['avg_latency'] = statistics.mean(latencies)
            analysis['summary']['p95_latency'] = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 10 else max(latencies)
        
        if memory_metrics:
            memories = [m['memory'] for m in memory_metrics]
            analysis['summary']['avg_memory'] = statistics.mean(memories)
            analysis['summary']['peak_memory'] = max(memories)
        
        # Identify bottlenecks
        self._identify_bottlenecks(analysis, throughput_metrics, latency_metrics, memory_metrics)
        
        # Generate recommendations
        self._generate_recommendations(analysis, results)
        
        return analysis
    
    def _identify_bottlenecks(self, analysis, throughput_metrics, latency_metrics, memory_metrics):
        """Identify performance bottlenecks."""
        # Low throughput bottlenecks
        if throughput_metrics:
            avg_throughput = statistics.mean([m['throughput'] for m in throughput_metrics])
            for metric in throughput_metrics:
                if metric['throughput'] < avg_throughput * 0.5:
                    analysis['bottlenecks'].append({
                        'type': 'Low Throughput',
                        'benchmark': metric['benchmark'],
                        'value': metric['throughput'],
                        'severity': 'High' if metric['throughput'] < avg_throughput * 0.25 else 'Medium'
                    })
        
        # High latency bottlenecks
        if latency_metrics:
            avg_latency = statistics.mean([m['latency'] for m in latency_metrics])
            for metric in latency_metrics:
                if metric['latency'] > avg_latency * 2:
                    analysis['bottlenecks'].append({
                        'type': 'High Latency',
                        'benchmark': metric['benchmark'],
                        'value': metric['latency'],
                        'severity': 'High' if metric['latency'] > avg_latency * 5 else 'Medium'
                    })
        
        # High memory usage
        if memory_metrics:
            for metric in memory_metrics:
                if metric['memory'] > 100:  # > 100 MB
                    analysis['bottlenecks'].append({
                        'type': 'High Memory Usage',
                        'benchmark': metric['benchmark'],
                        'value': metric['memory'],
                        'severity': 'High' if metric['memory'] > 500 else 'Medium'
                    })
    
    def _generate_recommendations(self, analysis, results):
        """Generate performance optimization recommendations."""
        recommendations = []
        
        # Database performance recommendations
        db_benchmarks = [name for name in results.keys() if 'Database' in name]
        if db_benchmarks:
            recommendations.append({
                'area': 'Database',
                'recommendation': 'Consider adding database indexes on frequently queried columns',
                'impact': 'Medium',
                'effort': 'Low'
            })
            recommendations.append({
                'area': 'Database',
                'recommendation': 'Implement connection pooling for better concurrent performance',
                'impact': 'High',
                'effort': 'Medium'
            })
        
        # Model performance recommendations
        model_benchmarks = [name for name in results.keys() if 'Model' in name]
        if model_benchmarks:
            recommendations.append({
                'area': 'Model',
                'recommendation': 'Cache frequently accessed events in memory',
                'impact': 'Medium',
                'effort': 'Medium'
            })
            recommendations.append({
                'area': 'Model',
                'recommendation': 'Use more efficient data structures (e.g., hash maps for O(1) lookups)',
                'impact': 'Medium',
                'effort': 'High'
            })
        
        # API performance recommendations
        api_benchmarks = [name for name in results.keys() if 'Api' in name]
        if api_benchmarks:
            recommendations.append({
                'area': 'API',
                'recommendation': 'Implement response caching for read-heavy endpoints',
                'impact': 'High',
                'effort': 'Medium'
            })
            recommendations.append({
                'area': 'API',
                'recommendation': 'Add request batching for bulk operations',
                'impact': 'Medium',
                'effort': 'Medium'
            })
        
        # Memory recommendations
        if any(b.get('type') == 'High Memory Usage' for b in analysis.get('bottlenecks', [])):
            recommendations.append({
                'area': 'Memory',
                'recommendation': 'Implement object pooling to reduce allocation overhead',
                'impact': 'Medium',
                'effort': 'High'
            })
        
        analysis['recommendations'] = recommendations
    
    def generate_report(self, results: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Generate a comprehensive performance report."""
        report = []
        report.append("=" * 60)
        report.append("         SCHEDULER PERFORMANCE ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Summary
        report.append("PERFORMANCE SUMMARY")
        report.append("-" * 20)
        summary = analysis.get('summary', {})
        if 'avg_throughput' in summary:
            report.append(f"Average Throughput: {summary['avg_throughput']:.2f} ops/sec")
            report.append(f"Throughput Range: {summary['min_throughput']:.2f} - {summary['max_throughput']:.2f} ops/sec")
        
        if 'avg_latency' in summary:
            report.append(f"Average Latency: {summary['avg_latency']:.2f} ms")
            if 'p95_latency' in summary:
                report.append(f"P95 Latency: {summary['p95_latency']:.2f} ms")
        
        if 'avg_memory' in summary:
            report.append(f"Average Memory Usage: {summary['avg_memory']:.2f} MB")
            report.append(f"Peak Memory Usage: {summary['peak_memory']:.2f} MB")
        
        report.append("")
        
        # Detailed Results
        report.append("BENCHMARK RESULTS")
        report.append("-" * 18)
        for benchmark, metrics in results.items():
            report.append(f"\n{benchmark}:")
            for metric, value in metrics.items():
                if isinstance(value, float):
                    report.append(f"  {metric}: {value:.3f}")
                else:
                    report.append(f"  {metric}: {value}")
        
        # Bottlenecks
        bottlenecks = analysis.get('bottlenecks', [])
        if bottlenecks:
            report.append("\nPERFORMANCE BOTTLENECKS")
            report.append("-" * 22)
            for bottleneck in bottlenecks:
                severity_marker = "⚠️" if bottleneck['severity'] == 'High' else "ℹ️"
                report.append(f"{severity_marker} {bottleneck['type']} in {bottleneck['benchmark']}")
                report.append(f"   Value: {bottleneck['value']:.2f}")
                report.append(f"   Severity: {bottleneck['severity']}")
                report.append("")
        
        # Recommendations
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            report.append("OPTIMIZATION RECOMMENDATIONS")
            report.append("-" * 29)
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i}. {rec['area']}: {rec['recommendation']}")
                report.append(f"   Impact: {rec['impact']} | Effort: {rec['effort']}")
                report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def export_json_summary(self, results: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Export results and analysis as JSON."""
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'analysis': analysis
        }
        return json.dumps(export_data, indent=2)
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check current system resource usage."""
        import psutil
        
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None
        }

def main():
    parser = argparse.ArgumentParser(description='Scheduler Performance Dashboard')
    parser.add_argument('--results-dir', default='benchmark_results',
                       help='Directory containing benchmark results')
    parser.add_argument('--output', choices=['console', 'file', 'json'],
                       default='console', help='Output format')
    parser.add_argument('--output-file', help='Output file path')
    
    args = parser.parse_args()
    
    analyzer = PerformanceAnalyzer(args.results_dir)
    
    print("🚀 Loading benchmark results...")
    results = analyzer.load_csv_results()
    
    if not results:
        print("❌ No benchmark results found. Run benchmarks first with: make benchmark && ./benchmark")
        return
    
    print(f"📊 Analyzing {len(results)} benchmark results...")
    analysis = analyzer.analyze_performance_trends(results)
    
    if args.output == 'console':
        report = analyzer.generate_report(results, analysis)
        print(report)
        
        # System resources
        try:
            import psutil
            print("\nCURRENT SYSTEM RESOURCES")
            print("-" * 24)
            resources = analyzer.check_system_resources()
            print(f"CPU Usage: {resources['cpu_percent']:.1f}%")
            print(f"Memory Usage: {resources['memory_percent']:.1f}%")
            print(f"Disk Usage: {resources['disk_usage']:.1f}%")
            if resources['load_average']:
                print(f"Load Average: {resources['load_average'][0]:.2f}")
        except ImportError:
            print("\n💡 Install 'psutil' for system resource monitoring: pip3 install psutil")
    
    elif args.output == 'json':
        json_output = analyzer.export_json_summary(results, analysis)
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(json_output)
            print(f"✅ JSON report saved to {args.output_file}")
        else:
            print(json_output)
    
    elif args.output == 'file':
        report = analyzer.generate_report(results, analysis)
        output_file = args.output_file or f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"✅ Report saved to {output_file}")

if __name__ == '__main__':
    main()