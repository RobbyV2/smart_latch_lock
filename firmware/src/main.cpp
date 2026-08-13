#include <Arduino.h>
#include <driver/gpio.h>
#include "pins.h"
#include "motor.h"
#include "lock.h"
#include "ble.h"
#include "web.h"

void setup() {
  Serial.begin(115200);
  setCpuFrequencyMhz(80);
  gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  motorInit();
  bleInit();
  webInit();
  lockInit();
  vTaskDelete(nullptr);
}

void loop() {}
