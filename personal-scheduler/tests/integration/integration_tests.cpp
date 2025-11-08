#include <cassert>
#include <thread>
#include <cstdio>
#include "../../api/ApiServer.h"
#include "../../controller/Controller.h"
#include "../../view/TextualView.h"
#include "../../database/SQLiteScheduleDatabase.h"
#include "../../model/Model.h"
#include "../../external/json/nlohmann/json.hpp"
#include "../../api/httplib.h"

using json = nlohmann::json;
using namespace std;
using namespace chrono;

static void runServer(ApiServer &srv) {
    srv.start();
}

static const char *API_KEY_VAL = "secret";

int main() {
    const char *path = "integration_test.db";
    std::remove(path);

    setenv("API_KEY", API_KEY_VAL, 1);
    SQLiteScheduleDatabase db(path);
    Model model(&db);
    TextualView view(model);
    Controller controller(model, view);
    ApiServer srv(model, 8099);
    thread th(runServer, std::ref(srv));
    this_thread::sleep_for(milliseconds(100));

    // simulate CLI input to add one event
    string input = "addat\nTitle1\nDesc1\n2025-06-05 12:30\nquit\n";
    istringstream iss(input);
    auto *cinBuf = cin.rdbuf();
    cin.rdbuf(iss.rdbuf());
    controller.run();
    cin.rdbuf(cinBuf);

    httplib::Client cli("localhost", 8099);
    httplib::Headers h{{"Authorization", API_KEY_VAL}};
    auto res = cli.Get("/events", h);
    assert(res && res->status == 200);
    json j = json::parse(res->body);
    assert(j["status"] == "ok");
    assert(j["data"].size() == 1);
    string id = j["data"][0]["id"];
    assert(j["data"][0]["title"] == "Title1");
    assert(j["data"][0]["description"] == "Desc1");
    assert(j["data"][0]["time"] == "2025-06-05 12:30");

    auto res2 = cli.Delete( ("/events/" + id).c_str(), h );
    assert(res2 && res2->status == 200);
    json j2 = json::parse(res2->body);
    assert(j2["status"] == "ok");

    auto res3 = cli.Get("/events", h);
    assert(res3 && res3->status == 200);
    json j3 = json::parse(res3->body);
    assert(j3["data"].size() == 0);

    srv.stop();
    th.join();
    std::remove(path);
    cout << "Integration tests passed\n";
    return 0;
}
