#include <Arduino.h>
#include <driver/gpio.h>
#include "pins.h"
#include "motor.h"
#include "lock.h"
#include "ble.h"

void setup() {
  Serial.begin(115200);
  setCpuFrequencyMhz(80);
  gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  motorInit();
  bleInit();
  if (!digitalRead(PIN_BUTTON)) {
    uint32_t t0 = millis();
    while (!digitalRead(PIN_BUTTON)) {
      if (millis() - t0 >= BOND_CLEAR_HOLD_MS) {
        bleClearBonds();
        break;
      }
      delay(10);
    }
  }
  lockInit();
  vTaskDelete(nullptr);
}

void loop() {}
