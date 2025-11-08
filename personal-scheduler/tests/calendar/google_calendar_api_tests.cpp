#include <cassert>
#include <fstream>
#include <thread>
#include "../../calendar/GoogleCalendarApi.h"
#include "../../model/OneTimeEvent.h"
#include <chrono>

using namespace std;

static const string scriptPath = "tests/calendar/env_report.py";

static void readFile(const string& path, string& out) {
    ifstream f(path);
    assert(f.good());
    getline(f, out, '\0');
    f.close();
}

static void testSequentialIsolation() {
    remove("tests/calendar/out1.txt");
    remove("tests/calendar/out2.txt");
    // First call
    GoogleCalendarApi api1("cred1", "cal1", scriptPath);
    OneTimeEvent ev1("1", "tests/calendar/out1.txt", "first",
                     chrono::system_clock::now(), chrono::minutes(1));
    api1.addEvent(ev1);
    assert(getenv("GCAL_CREDS") == nullptr);
    string r1; readFile("tests/calendar/out1.txt", r1);
    assert(r1.find("cred1") != string::npos);
    // Second call with different creds
    GoogleCalendarApi api2("cred2", "cal1", scriptPath);
    OneTimeEvent ev2("2", "tests/calendar/out2.txt", "second",
                     chrono::system_clock::now(), chrono::minutes(1));
    api2.addEvent(ev2);
    assert(getenv("GCAL_CREDS") == nullptr);
    string r2; readFile("tests/calendar/out2.txt", r2);
    assert(r2.find("cred2") != string::npos);
}

static void worker(const string& cred, const string& tag, const string& path) {
    GoogleCalendarApi api(cred, "cal1", scriptPath);
    OneTimeEvent ev(tag, path, tag, chrono::system_clock::now(), chrono::minutes(1));
    api.addEvent(ev);
}

static void testConcurrentIsolation() {
    string p1 = "tests/calendar/outA.txt";
    string p2 = "tests/calendar/outB.txt";
    remove(p1.c_str());
    remove(p2.c_str());
    thread t1(worker, "credA", "A", p1);
    thread t2(worker, "credB", "B", p2);
    t1.join();
    t2.join();
    string r1; readFile(p1, r1);
    string r2; readFile(p2, r2);
    assert(r1.find("credA") != string::npos);
    assert(r2.find("credB") != string::npos);
    assert(getenv("GCAL_CREDS") == nullptr);
}

int main(){
    testSequentialIsolation();
    testConcurrentIsolation();
    cout << "GoogleCalendarApi tests passed\n";
    return 0;
}
