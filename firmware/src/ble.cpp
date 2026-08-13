#include <NimBLEDevice.h>
#include <esp_timer.h>
#include "pins.h"
#include "ble.h"
#include "lock.h"
#include "motor.h"

static NimBLECharacteristic* stateChr;
static NimBLECharacteristic* battChr;
static NimBLEAdvertising* adv;
static bool paired;
static uint8_t lastPct = 255;

static void advIntervals() {
  if (paired) {
    adv->setMinInterval(1600);
    adv->setMaxInterval(1680);
  } else {
    adv->setMinInterval(160);
    adv->setMaxInterval(240);
  }
}

static uint8_t battPct() {
  int p = (batteryMv() - 3300) * 100 / 900;
  return (uint8_t)(p < 0 ? 0 : p > 100 ? 100 : p);
}

static void battUpdate() {
  uint8_t p = battPct();
  battChr->setValue(&p, 1);
  int last = lastPct;
  if (last == 255 || abs((int)p - last) >= 2) {
    battChr->notify();
    lastPct = p;
  }
}

struct CmdCb : NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
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
  void onConnect(NimBLEServer*, NimBLEConnInfo&) override {
    lastPct = 255;
    battUpdate();
  }
  void onAuthenticationComplete(NimBLEConnInfo& ci) override {
    if (!ci.isBonded()) return;
    NimBLEDevice::whiteListAdd(ci.getIdAddress());
    paired = true;
    adv->stop();
    adv->setScanFilter(true, true);
    advIntervals();
    adv->start();
  }
};

static CmdCb cmdCb;
static SrvCb srvCb;

void bleInit() {
  NimBLEDevice::init("ArcLock");
  NimBLEDevice::setSecurityAuth(true, true, true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
  NimBLEDevice::setSecurityPasskey(BLE_PASSKEY);
  NimBLEServer* srv = NimBLEDevice::createServer();
  srv->setCallbacks(&srvCb);
  srv->advertiseOnDisconnect(true);
  NimBLEService* svc = srv->createService(UUID_SVC);
  NimBLECharacteristic* cmd = svc->createCharacteristic(
      UUID_CMD, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN);
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
  int n = NimBLEDevice::getNumBonds();
  paired = n > 0;
  for (int i = 0; i < n; i++) NimBLEDevice::whiteListAdd(NimBLEDevice::getBondedAddress(i));
  if (paired) adv->setScanFilter(true, true);
  advIntervals();
  adv->start();
  battUpdate();
  static esp_timer_handle_t bt;
  esp_timer_create_args_t a = {};
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

bool blePairing() { return !paired; }

void bleClearBonds() {
  NimBLEDevice::deleteAllBonds();
  while (NimBLEDevice::getWhiteListCount() > 0)
    NimBLEDevice::whiteListRemove(NimBLEDevice::getWhiteListAddress(0));
  paired = false;
  adv->stop();
  adv->setScanFilter(false, false);
  advIntervals();
  adv->start();
}
