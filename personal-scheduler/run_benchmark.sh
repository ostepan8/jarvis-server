#!/bin/bash

echo "🚀 Unified Scheduler Benchmark Runner"
echo "====================================="

# Build benchmark if needed
if [ ! -f "./benchmark" ]; then
    echo "Building benchmark tool..."
    make benchmark
    if [ $? -ne 0 ]; then
        echo "❌ Failed to build benchmark"
        exit 1
    fi
fi

# Parse arguments
case "${1:-all}" in
    "model")
        echo "Running model benchmarks..."
        ./benchmark --model
        ;;
    "api") 
        echo "Running API benchmarks..."
        ./benchmark --api
        ;;
    "full")
        echo "Running full system benchmark..."
        ./benchmark --full
        ;;
    "all"|"")
        echo "Running all benchmarks..."
        ./benchmark
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [model|api|full|all]"
        echo ""
        echo "Options:"
        echo "  model    - Test event creation and retrieval performance"
        echo "  api      - Test HTTP API performance and caching" 
        echo "  full     - Complete system load test"
        echo "  all      - Run all benchmark suites (default)"
        echo "  help     - Show this help"
        exit 0
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac

echo "✅ Benchmark completed!"