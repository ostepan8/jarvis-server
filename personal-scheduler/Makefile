# Unified Scheduler Makefile
CXX       = g++
CXXFLAGS  = -std=c++17 -Wall -pthread -Iapi -Iexternal/json -Ischeduler -MMD -MP
LIBS      = -lsqlite3 -pthread -lcurl

# Core source files
CORE_SRCS = controller/Controller.cpp \
           model/Model.cpp \
           model/OneTimeEvent.cpp \
           model/RecurringEvent.cpp \
           model/recurrence/DailyRecurrence.cpp \
           model/recurrence/WeeklyRecurrence.cpp \
           model/recurrence/MonthlyRecurrence.cpp \
           model/recurrence/YearlyRecurrence.cpp \
           view/TextualView.cpp \
           api/routing/Router.cpp \
           api/performance/PerformanceMonitor.cpp \
           api/routes/EventRoutes.cpp \
           api/routes/RecurringRoutes.cpp \
           api/routes/AvailabilityRoutes.cpp \
           api/routes/StatsRoutes.cpp \
           api/routes/TaskRoutes.cpp \
           api/routes/WakeRoutes.cpp \
           services/EventService.cpp \
           database/SQLiteScheduleDatabase.cpp \
           database/SettingsStore.cpp \
           scheduler/EventLoop.cpp \
           processing/WakeScheduler.cpp \
           calendar/GoogleCalendarApi.cpp \
           utils/EnvLoader.cpp \
           utils/Logger.cpp \
           utils/FastSerializer.cpp \
           utils/ResponseCache.cpp \
           security/Auth.cpp \
           security/RateLimiter.cpp

# Application source files
APP_SRCS = main.cpp $(CORE_SRCS)
BENCHMARK_SRCS = benchmark.cpp $(CORE_SRCS)

# Test source files
TEST_SRCS = $(CORE_SRCS)
EVENT_SERVICE_TEST_SRCS = tests/services/event_service_tests.cpp $(TEST_SRCS)
HANDLERS_TEST_SRCS = tests/api/handlers_tests.cpp $(TEST_SRCS)
ROUTER_TEST_SRCS = tests/api/router_tests.cpp $(TEST_SRCS)
SECURITY_TEST_SRCS = tests/security/security_tests.cpp $(TEST_SRCS)

# Object files
APP_OBJS = $(APP_SRCS:.cpp=.o)
BENCHMARK_OBJS = $(BENCHMARK_SRCS:.cpp=.o)
EVENT_SERVICE_TEST_OBJS = $(EVENT_SERVICE_TEST_SRCS:.cpp=.o)
HANDLERS_TEST_OBJS = $(HANDLERS_TEST_SRCS:.cpp=.o)
ROUTER_TEST_OBJS = $(ROUTER_TEST_SRCS:.cpp=.o)
SECURITY_TEST_OBJS = $(SECURITY_TEST_SRCS:.cpp=.o)

# Targets
SERVER_TARGET = scheduler_server
BENCHMARK_TARGET = benchmark
EVENT_SERVICE_TEST_TARGET = event_service_tests
HANDLERS_TEST_TARGET = handlers_tests
ROUTER_TEST_TARGET = router_tests
SECURITY_TEST_TARGET = security_tests

.PHONY: all clean server benchmark test unit-tests install help \
        $(EVENT_SERVICE_TEST_TARGET) $(HANDLERS_TEST_TARGET) $(ROUTER_TEST_TARGET) $(SECURITY_TEST_TARGET)

all: server

server: $(SERVER_TARGET)
	@echo "Built SOLID-compliant scheduler server"

benchmark: $(BENCHMARK_TARGET)
	@echo "Built performance benchmark"

$(SERVER_TARGET): $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

$(BENCHMARK_TARGET): $(BENCHMARK_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

# Test targets
$(EVENT_SERVICE_TEST_TARGET): $(EVENT_SERVICE_TEST_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

$(HANDLERS_TEST_TARGET): $(HANDLERS_TEST_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

$(ROUTER_TEST_TARGET): $(ROUTER_TEST_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

$(SECURITY_TEST_TARGET): $(SECURITY_TEST_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

# Include dependency files  
-include $(APP_OBJS:.o=.d) $(BENCHMARK_OBJS:.o=.d) \
         $(EVENT_SERVICE_TEST_OBJS:.o=.d) $(HANDLERS_TEST_OBJS:.o=.d) \
         $(ROUTER_TEST_OBJS:.o=.d) $(SECURITY_TEST_OBJS:.o=.d)

# Pattern rule for object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

test: benchmark
	@echo "Running performance benchmark..."
	./$(BENCHMARK_TARGET)

unit-tests: $(EVENT_SERVICE_TEST_TARGET) $(HANDLERS_TEST_TARGET) $(ROUTER_TEST_TARGET) $(SECURITY_TEST_TARGET)
	@echo "Running unit tests..."
	@echo "Running EventService tests..."
	./$(EVENT_SERVICE_TEST_TARGET)
	@echo "Running Handlers tests..."
	./$(HANDLERS_TEST_TARGET)
	@echo "Running Router tests..."
	./$(ROUTER_TEST_TARGET)
	@echo "Running Security tests..."
	./$(SECURITY_TEST_TARGET)
	@echo "All unit tests completed!"

clean:
	rm -f $(APP_OBJS) $(BENCHMARK_OBJS)
	rm -f $(EVENT_SERVICE_TEST_OBJS) $(HANDLERS_TEST_OBJS) $(ROUTER_TEST_OBJS) $(SECURITY_TEST_OBJS)
	rm -f $(APP_OBJS:.o=.d) $(BENCHMARK_OBJS:.o=.d)  
	rm -f $(EVENT_SERVICE_TEST_OBJS:.o=.d) $(HANDLERS_TEST_OBJS:.o=.d) \
	      $(ROUTER_TEST_OBJS:.o=.d) $(SECURITY_TEST_OBJS:.o=.d)
	rm -f ./$(SERVER_TARGET) ./$(BENCHMARK_TARGET)
	rm -f $(EVENT_SERVICE_TEST_TARGET) $(HANDLERS_TEST_TARGET) $(ROUTER_TEST_TARGET) $(SECURITY_TEST_TARGET)
	@echo "Cleaned build artifacts"

install: server
	@echo "Installing scheduler to /usr/local/bin (requires sudo)"
	sudo cp $(SERVER_TARGET) /usr/local/bin/

help:
	@echo "Available targets:"
	@echo "  all        - Build the SOLID-compliant scheduler server (default)"
	@echo "  server     - Build the scheduler server"
	@echo "  benchmark  - Build the performance benchmark tool"
	@echo "  test       - Run the performance benchmark"
	@echo "  unit-tests - Build and run all unit tests"
	@echo "  clean      - Remove build artifacts"
	@echo "  install    - Install to /usr/local/bin"
	@echo "  help       - Show this help message"
	@echo ""
	@echo "Individual test targets:"
	@echo "  event_service_tests - Test EventService component"
	@echo "  handlers_tests      - Test API handlers"
	@echo "  router_tests        - Test Router component"
	@echo "  security_tests      - Test Auth and RateLimiter"
	@echo ""
	@echo "Server follows SOLID principles:"
	@echo "  ./scheduler_server    - Run SOLID-compliant server"
	@echo ""
	@echo "Benchmark usage:"
	@echo "  ./benchmark           - Run all benchmarks"
	@echo "  ./benchmark --model   - Run model benchmarks only"
	@echo "  ./benchmark --api     - Run API benchmarks only"
	@echo "  ./benchmark --full    - Run full system benchmark only"