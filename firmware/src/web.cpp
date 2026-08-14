#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <esp_timer.h>
#include <esp_mac.h>
#include "web.h"
#include "ble.h"
#include "lock.h"
#include "motor.h"

static WebServer server(80);
static Preferences store;
static char ssid[12];
static String apPass;
static esp_timer_handle_t apTimer;

static const char PAGE[] = R"html(<!doctype html>
<html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Lock</title><style>
body{font-family:system-ui;max-width:26rem;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}
h1{font-size:1.3rem}h2{font-size:1rem;margin-top:1.5rem;border-top:1px solid #333;padding-top:1rem}
button{background:#2563eb;color:#fff;border:0;border-radius:.4rem;padding:.6rem 1.2rem;margin:.2rem .4rem .2rem 0;font-size:1rem}
button.warn{background:#b91c1c}
input{background:#222;color:#eee;border:1px solid #444;border-radius:.4rem;padding:.5rem;font-size:1rem}
#state{font-size:1.6rem;font-weight:600}
.dim{color:#888;font-size:.85rem}
</style></head><body>
<h1>Lock</h1>
<div id=state>...</div>
<div id=batt class=dim></div>
<div id=chg class=dim style=display:none>charging, lock disabled</div>
<p><button onclick="post('/api/lock')">Lock</button><button onclick="post('/api/unlock')">Unlock</button></p>
<h2>WiFi</h2>
<input id=pw type=password placeholder="AP password, min 8 chars">
<button onclick=setPw()>Set</button>
<p class=dim>Saving restarts the AP with WPA2; reconnect with the new password.</p>
<h2>Master Device</h2>
<div id=master class=dim></div>
<p><button class=warn onclick="post('/api/master/delete')">Delete master</button>
<button id=adopt onclick="post('/api/master/adopt')">Adopt next</button></p>
<p class=dim>The first device to connect and bond while no master is stored becomes the master. Its presence enables the physical button.</p>
<script>
const S=['Unlocked','Closing','Seating','Locked','Unlatching','Opening','Fault: obstructed','Fault: timeout'];
async function post(u){await fetch(u,{method:'POST'});poll()}
async function setPw(){const p=document.getElementById('pw').value;
const r=await fetch('/api/wifi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pass:p})});
alert(r.ok?'Saved, AP restarting':'Password must be at least 8 characters')}
async function poll(){try{
const s=await(await fetch('/api/state')).json();
document.getElementById('state').textContent=S[s.state]||s.state;
document.getElementById('batt').textContent='Battery '+s.batt+'%'+(s.faults?' / faults 0x'+s.faults.toString(16):'');
document.getElementById('chg').style.display=s.charging?'':'none';
const m=await(await fetch('/api/master')).json();
document.getElementById('master').textContent=m.addr?m.addr+(m.connected?' / connected':' / away'):'none stored';
document.getElementById('adopt').textContent=m.adopt?'Adopt next: armed':'Adopt next';
}catch(e){}}
poll();setInterval(poll,2000);
</script></body></html>)html";

static void apStart() {
  WiFi.softAP(ssid, apPass.length() >= 8 ? apPass.c_str() : nullptr);
}

static String jsonField(const String& b, const char* key) {
  int k = b.indexOf(String('"') + key + '"');
  if (k < 0) return "";
  int a = b.indexOf('"', b.indexOf(':', k) + 1);
  if (a < 0) return "";
  int e = b.indexOf('"', a + 1);
  return e < 0 ? String("") : b.substring(a + 1, e);
}

static bool sameOrigin() {
  String o = server.header("Origin");
  if (o.length() == 0 || o == "http://192.168.4.1") return true;
  server.send(403);
  return false;
}

static void handlers() {
  server.on("/", HTTP_GET, [] { server.send(200, "text/html", PAGE); });
  server.on("/api/state", HTTP_GET, [] {
    char b[96];
    snprintf(b, sizeof b, "{\"state\":%u,\"faults\":%u,\"batt\":%u,\"charging\":%s}", lockState(), lockFaults(),
             batteryPct(), vbusPresent() ? "true" : "false");
    server.send(200, "application/json", b);
  });
  server.on("/api/lock", HTTP_POST, [] {
    if (!sameOrigin()) return;
    lockPost(Event::CmdLock);
    server.send(200);
  });
  server.on("/api/unlock", HTTP_POST, [] {
    if (!sameOrigin()) return;
    lockPost(Event::CmdUnlock);
    server.send(200);
  });
  server.on("/api/wifi", HTTP_POST, [] {
    if (!sameOrigin()) return;
    if (!server.header("Content-Type").startsWith("application/json")) {
      server.send(415);
      return;
    }
    String p = jsonField(server.arg("plain"), "pass");
    if (p.length() < 8) {
      server.send(400, "text/plain", "min 8 chars");
      return;
    }
    store.putString("appass", p);
    apPass = p;
    server.send(200);
    esp_timer_start_once(apTimer, 500000);
  });
  server.on("/api/master", HTTP_GET, [] {
    char b[96];
    snprintf(b, sizeof b, "{\"addr\":\"%s\",\"connected\":%s,\"adopt\":%s}", bleMasterAddr().c_str(),
             bleMasterPresent() ? "true" : "false", bleAdoptArmed() ? "true" : "false");
    server.send(200, "application/json", b);
  });
  server.on("/api/master/delete", HTTP_POST, [] {
    if (!sameOrigin()) return;
    bleMasterDelete();
    server.send(200);
  });
  server.on("/api/master/adopt", HTTP_POST, [] {
    if (!sameOrigin()) return;
    bleAdoptToggle();
    server.send(200);
  });
}

void webInit() {
  store.begin("lock", false);
  apPass = store.getString("appass", "");
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
  snprintf(ssid, sizeof ssid, "lock-%02X%02X", mac[4], mac[5]);
  WiFi.mode(WIFI_AP);
  apStart();
  handlers();
  static const char* hdrs[] = {"Origin", "Content-Type"};
  server.collectHeaders(hdrs, 2);
  server.begin();
  esp_timer_create_args_t a = {};
  a.callback = [](void*) { apStart(); };
  a.name = "ap";
  esp_timer_create(&a, &apTimer);
  xTaskCreate(
      [](void*) {
        for (;;) {
          server.handleClient();
          vTaskDelay(pdMS_TO_TICKS(20));
        }
      },
      "web", 4096, nullptr, 1, nullptr);
}
