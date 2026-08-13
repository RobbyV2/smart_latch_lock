#include <NimBLEDevice.h>
#include <Preferences.h>
#include <esp_timer.h>
#include "pins.h"
#include "ble.h"
#include "lock.h"
#include "motor.h"

static NimBLECharacteristic* stateChr;
static NimBLECharacteristic* battChr;
static NimBLEAdvertising* adv;
static NimBLEServer* srv;
static Preferences store;
static NimBLEAddress master;
static bool haveMaster, adoptArmed;
static volatile uint16_t masterConn = BLE_HS_CONN_HANDLE_NONE;
static volatile uint16_t graceConn = BLE_HS_CONN_HANDLE_NONE;
static esp_timer_handle_t graceTimer;
static uint8_t lastPct = 255;

static void advApply() {
  if (haveMaster) {
    adv->setMinInterval(1600);
    adv->setMaxInterval(1680);
  } else {
    adv->setMinInterval(160);
    adv->setMaxInterval(240);
  }
}

static void battUpdate() {
  uint8_t p = batteryPct();
  battChr->setValue(&p, 1);
  int last = lastPct;
  if (last == 255 || abs((int)p - last) >= 2) {
    battChr->notify();
    lastPct = p;
  }
}

static void graceCb(void*) {
  uint16_t c = graceConn;
  if (c != BLE_HS_CONN_HANDLE_NONE && c != masterConn) srv->disconnect(c);
  graceConn = BLE_HS_CONN_HANDLE_NONE;
}

struct CmdCb : NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& ci) override {
    if (ci.getConnHandle() != masterConn || !ci.isEncrypted()) return;
    NimBLEAttValue v = c->getValue();
    if (v.size() != 1) return;
    switch (v[0]) {
      case 0x01: lockPost(Event::CmdLock); break;
      case 0x02: lockPost(Event::CmdUnlock); break;
      case 0x03: lockPost(Event::CmdClear); break;
      default: break;
    }
  }
};

struct SrvCb : NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& ci) override {
    lastPct = 255;
    battUpdate();
    NimBLEDevice::startSecurity(ci.getConnHandle());
    if (haveMaster && !adoptArmed) {
      graceConn = ci.getConnHandle();
      esp_timer_stop(graceTimer);
      esp_timer_start_once(graceTimer, BLE_GRACE_MS * 1000ULL);
    }
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo& ci, int) override {
    if (ci.getConnHandle() == masterConn) masterConn = BLE_HS_CONN_HANDLE_NONE;
    if (ci.getConnHandle() == graceConn) graceConn = BLE_HS_CONN_HANDLE_NONE;
  }
  void onAuthenticationComplete(NimBLEConnInfo& ci) override {
    if (!ci.isEncrypted() || !ci.isBonded()) return;
    NimBLEAddress id = ci.getIdAddress();
    if (haveMaster && id == master) {
      masterConn = ci.getConnHandle();
    } else if (!haveMaster || adoptArmed) {
      uint16_t old = masterConn;
      if (old != BLE_HS_CONN_HANDLE_NONE) srv->disconnect(old);
      if (haveMaster) NimBLEDevice::deleteBond(master);
      master = id;
      haveMaster = true;
      adoptArmed = false;
      masterConn = ci.getConnHandle();
      store.putBytes("master", master.getBase(), sizeof(ble_addr_t));
      advApply();
    } else {
      NimBLEDevice::deleteBond(id);
      srv->disconnect(ci.getConnHandle());
    }
  }
};

static CmdCb cmdCb;
static SrvCb srvCb;

void bleInit() {
  store.begin("lock", false);
  ble_addr_t b;
  if (store.getBytes("master", &b, sizeof b) == sizeof b) {
    master = NimBLEAddress(b);
    haveMaster = true;
  }
  NimBLEDevice::init("ArcLock");
  NimBLEDevice::setSecurityAuth(true, false, true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);
  srv = NimBLEDevice::createServer();
  srv->setCallbacks(&srvCb);
  srv->advertiseOnDisconnect(true);
  NimBLEService* svc = srv->createService(UUID_SVC);
  NimBLECharacteristic* cmd =
      svc->createCharacteristic(UUID_CMD, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC);
  cmd->setCallbacks(&cmdCb);
  stateChr = svc->createCharacteristic(
      UUID_STATE, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::NOTIFY);
  svc->start();
  NimBLEService* bs = srv->createService(NimBLEUUID((uint16_t)0x180F));
  battChr = bs->createCharacteristic(NimBLEUUID((uint16_t)0x2A19),
                                     NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  bs->start();
  adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(UUID_SVC);
  adv->setName("ArcLock");
  advApply();
  adv->start();
  battUpdate();
  esp_timer_create_args_t a = {};
  a.callback = graceCb;
  a.name = "grace";
  esp_timer_create(&a, &graceTimer);
  static esp_timer_handle_t bt;
  a.callback = [](void*) { battUpdate(); };
  a.name = "batt";
  esp_timer_create(&a, &bt);
  esp_timer_start_periodic(bt, 60000000ULL);
}

void bleNotifyState(uint8_t s, uint8_t f) {
  uint8_t v[2] = {s, f};
  stateChr->setValue(v, 2);
  stateChr->notify();
}

bool bleMasterStored() { return haveMaster; }
bool bleMasterPresent() { return masterConn != BLE_HS_CONN_HANDLE_NONE; }
bool bleAdoptArmed() { return adoptArmed; }
void bleAdoptToggle() { adoptArmed = !adoptArmed; }
std::string bleMasterAddr() { return haveMaster ? master.toString() : std::string(); }

void bleMasterDelete() {
  uint16_t c = masterConn;
  masterConn = BLE_HS_CONN_HANDLE_NONE;
  if (c != BLE_HS_CONN_HANDLE_NONE) srv->disconnect(c);
  NimBLEDevice::deleteAllBonds();
  haveMaster = false;
  store.remove("master");
  advApply();
}
