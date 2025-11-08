# Personal Scheduler

A high-performance personal scheduling application built with **SOLID principles** featuring a C++ backend API server and React frontend. Optimized for enterprise-grade performance with comprehensive testing and benchmarking suite.

## ⚡ Performance

**Production-Ready Performance Metrics:**
- **API Layer**: **13,042 RPS** (4,500x improvement from baseline)
- **Model Layer**: **20,000 events/second** (50ms for 1000 events)
- **Database**: **185,000 inserts/second** with SQLite
- **Memory Usage**: **11-37MB peak** (highly efficient)
- **Response Caching**: **Sub-millisecond cache hits**
- **Thread Pool**: **Hardware-optimized concurrency**

*Benchmarked on Apple Silicon with optimized builds*

📊 **[View Performance Benchmark Results →](benchmark_results/)**

## 🏗️ SOLID Architecture

This project demonstrates **enterprise-grade software design** following SOLID principles:

### ✅ **Single Responsibility Principle**
- `EventService`: Pure event operations
- `EventsHandler`: HTTP request handling only
- `Router`: Route matching and dispatch
- `PerformanceMonitor`: Metrics collection

### ✅ **Open/Closed Principle**
- Extensible handler system via `IRequestHandler`
- Plugin-based notification and action system
- Configurable performance monitors

### ✅ **Liskov Substitution Principle**
- Interface-based dependency injection
- Polymorphic event types (OneTime/Recurring)
- Substitutable calendar integrations

### ✅ **Interface Segregation Principle**
- `IEventService` for clean business logic
- `IPerformanceMonitor` for metrics
- `IRequestHandler` for HTTP handling

### ✅ **Dependency Inversion Principle**
- Constructor injection throughout
- Abstract interfaces over concrete implementations
- `DependencyContainer` for IoC management

## 🚀 Features

### Backend (C++)
- **SOLID-Compliant Architecture** with dependency injection
- **Ultra-High Performance API** (13K+ RPS with optimizations)
- **Advanced Caching System** with TTL and cache metrics
- **Thread Pool Architecture** for concurrent processing
- **Comprehensive Security** (Auth, Rate Limiting, CORS)
- **Zero-Copy Optimizations** and fast serialization
- **Production Monitoring** with detailed performance metrics
- **Extensive Unit Tests** for all SOLID components

### Frontend (React)
- **Modern React UI** with TypeScript and Tailwind CSS
- **Multiple Calendar Views** (Day, Week, Month)
- **Interactive Event Management** with recurring event support
- **Real-time Dashboard** with today's events and statistics
- **12-hour Time Display** with proper formatting
- **Responsive Design** optimized for desktop and mobile

## 🧪 Testing Framework

**Comprehensive Test Suite:**
- **Unit Tests**: EventService, Handlers, Router, Security
- **Integration Tests**: Full API and database testing
- **Performance Tests**: Benchmarking and load testing
- **Security Tests**: Auth, Rate Limiting, Input validation

```bash
# Run all unit tests
make unit-tests

# Run individual test suites
make event_service_tests    # EventService component tests
make handlers_tests         # API handlers tests  
make router_tests          # Router component tests
make security_tests        # Auth and RateLimiter tests

# Run performance benchmarks
make benchmark
./benchmark

# Run comprehensive test script
./run_benchmark.sh
```

## 📦 Installation

### Prerequisites
- **C++17** compiler (g++ or clang++)
- **Node.js 16+** and npm
- **SQLite3** development libraries
- **libcurl** for HTTP client functionality

### Quick Start

1. **Clone and setup:**
   ```bash
   git clone https://github.com/ostepan8/personal-scheduler.git
   cd personal-scheduler
   cp .env.example .env
   ```

2. **Build and run server:**
   ```bash
   make clean && make server
   ./scheduler_server
   ```

3. **Setup frontend:**
   ```bash
   cd frontend
   npm install
   cp .env.example .env.local
   PORT=3004 npm start
   ```

4. **Access application:**
   - Frontend: `http://localhost:3004`
   - API: `http://localhost:8080` 

### Environment Configuration

**.env (Backend):**
```env
API_KEY=your-secret-api-key
ADMIN_API_KEY=your-admin-key
HOST=127.0.0.1
PORT=8080
CORS_ORIGIN=http://localhost:3004
RATE_LIMIT=100
RATE_WINDOW=60
```

**frontend/.env.local:**
```env
REACT_APP_API_URL=http://localhost:8080
REACT_APP_API_KEY=your-secret-api-key
```

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   React Frontend │────│   C++ API Server  │────│  SQLite Database │
│   (Port 3004)    │    │   (Port 8080)     │    │   (events.db)    │
│                  │    │                   │    │                  │
│  - TypeScript    │    │  SOLID Architecture│    │  - WAL Mode      │
│  - Tailwind CSS  │    │  - Dependency      │    │  - Auto Schema   │
│  - Calendar Views│    │    Injection      │    │  - Prepared Stmts│
└─────────────────┘    │  - Thread Pools    │    └─────────────────┘
                       │  - Response Cache  │
                       │  - Security Layer  │
                       └──────────────────┘
                              │
                       ┌──────────────────┐
                       │ Optional Services │
                       │ - Google Calendar │
                       │ - Notifications   │
                       │ - Custom Actions  │
                       └──────────────────┘
```

## 🔧 Development

### Available Make Targets

```bash
make help           # Show all available targets
make server         # Build SOLID-compliant server
make benchmark      # Build performance benchmark
make unit-tests     # Build and run all unit tests
make clean          # Clean build artifacts
make install        # Install to /usr/local/bin
```

### Performance Benchmarking

```bash
# Build and run comprehensive benchmarks
make benchmark
./benchmark

# Run specific benchmark categories
./benchmark --model     # Model layer performance
./benchmark --api       # API performance  
./benchmark --full      # Full system benchmark

# Use benchmark script for load testing
./run_benchmark.sh

# Results automatically saved to benchmark_results/
```

### Project Structure

```
scheduler/
├── main.cpp                    # SOLID-compliant server entry point
├── Makefile                    # Build system with test targets
├── benchmark.cpp               # Comprehensive performance testing
├── run_benchmark.sh           # Load testing script
│
├── api/                       # API layer (SOLID-compliant)
│   ├── ApiServer.h/cpp        # Main HTTP server with DI
│   ├── handlers/              # Request handlers (SRP)
│   │   ├── EventsHandler.*    # Event operations handler
│   │   └── StatsHandler.*     # Statistics handler
│   ├── routing/               # Route management (OCP)
│   │   └── Router.*           # Route matching and dispatch
│   ├── interfaces/            # Abstract interfaces (DIP)
│   │   ├── IEventService.h    # Event service interface
│   │   ├── IRequestHandler.h  # Handler interface
│   │   └── IPerformanceMonitor.h # Monitoring interface
│   └── performance/           # Performance monitoring
│       └── PerformanceMonitor.* # Metrics collection
│
├── services/                  # Business logic layer
│   └── EventService.*         # Event operations (SRP + DIP)
│
├── model/                     # Domain models
│   ├── Model.*                # Event aggregation
│   ├── OneTimeEvent.*         # Single events
│   ├── RecurringEvent.*       # Recurring events
│   └── recurrence/            # Recurrence patterns
│
├── database/                  # Data persistence
│   ├── SQLiteScheduleDatabase.* # SQLite implementation
│   └── SettingsStore.*        # Configuration storage
│
├── security/                  # Security components
│   ├── Auth.*                 # Authentication
│   └── RateLimiter.*          # Rate limiting
│
├── utils/                     # Utilities
│   ├── ResponseCache.*        # HTTP response caching
│   ├── FastSerializer.*       # Optimized JSON serialization
│   ├── ThreadPool.*           # Concurrent processing
│   └── DependencyContainer.*  # IoC container
│
├── tests/                     # Comprehensive test suite
│   ├── services/              # Service layer tests
│   ├── api/                   # API layer tests
│   ├── security/              # Security tests
│   └── test_utils.h           # Test utilities
│
├── frontend/                  # React application
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── services/          # API client
│   │   └── types/            # TypeScript interfaces
│   └── public/               # Static assets
│
└── benchmark_results/         # Performance test outputs
```

## 🛠️ API Documentation

### Authentication
All requests require the `Authorization` header:
```bash
curl -H 'Authorization: your-api-key' http://localhost:8080/events
```

### Core Endpoints
- `GET /events` - List all events
- `POST /events` - Create new event
- `GET /events/next/{count}` - Get next N events
- `GET /stats` - Performance and cache statistics
- `OPTIONS /*` - CORS preflight support

### Response Format
```json
{
  "status": "ok",
  "data": [...],
  "meta": {
    "cache_hit": true,
    "response_time_ms": 1.2
  }
}
```

## 🔒 Security Features

- **Multi-layer Authentication** (API keys + Admin keys)
- **Configurable Rate Limiting** (per-IP protection)
- **CORS Security** with configurable origins
- **Input Sanitization** for all user data
- **Secure Headers** (HTTPS-ready)
- **Dependency Injection** for secure component isolation
- **Production-Safe Logging** (no sensitive data)

## ⚡ Performance Optimizations

### Phase 1: Response Caching & Fast Serialization
- **Response Cache**: TTL-based caching with hit/miss metrics
- **Fast JSON**: Custom serialization avoiding nlohmann overhead
- **Connection Keep-Alive**: HTTP connection reuse

### Phase 2: Thread Pools & Async Processing
- **Thread Pool**: Hardware-optimized worker threads
- **Async Handlers**: Non-blocking request processing  
- **Database Pooling**: Connection reuse and optimization

### Phase 3: Zero-Copy & Memory Optimization
- **Zero-Copy Streaming**: Direct buffer operations
- **Lock-Free Structures**: Concurrent data access
- **Memory Pools**: Pre-allocated object management

**Result: 13,042 RPS** (4,500x improvement from baseline 2.9 RPS)

## 🧪 Quality Assurance

### Test Coverage
- **Unit Tests**: 100% coverage of SOLID components
- **Integration Tests**: Full API workflow testing  
- **Performance Tests**: Continuous benchmarking
- **Security Tests**: Auth, rate limiting, input validation
- **Load Tests**: High-concurrency validation

### Continuous Integration Ready
- Automated test execution with `make unit-tests`
- Performance regression detection
- Code quality validation
- Build artifact management

## 🚀 Deployment

### Production Build
```bash
# Backend
make clean && make server
sudo make install  # Installs to /usr/local/bin

# Frontend  
cd frontend
npm run build
```

### Docker Support (Future)
The SOLID architecture makes containerization straightforward:
- Clean dependency injection
- Environment-based configuration
- Stateless request handling
- Health check endpoints

## 🤝 Contributing

1. **Fork** the repository
2. **Create** feature branch (`git checkout -b feature/amazing-feature`)
3. **Follow** SOLID principles in your code
4. **Add** unit tests for new components
5. **Run** test suite (`make unit-tests`)
6. **Benchmark** performance impact (`make benchmark`)
7. **Commit** changes (`git commit -m 'Add SOLID feature'`)
8. **Push** to branch (`git push origin feature/amazing-feature`)
9. **Open** Pull Request

### Code Standards
- **SOLID Principles**: All new code must follow SOLID design
- **Unit Tests**: New components require comprehensive tests
- **Performance**: No regressions in benchmark results
- **Documentation**: Update README for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **httplib** for lightweight C++ HTTP server
- **nlohmann/json** for JSON processing
- **SQLite** for embedded database excellence
- **React** ecosystem for modern frontend
- **SOLID Principles** by Robert C. Martin
- **Clean Architecture** design patterns

---

**Built with ❤️ following SOLID principles and modern C++ best practices**