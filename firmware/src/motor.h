#pragma once
#include <stdint.h>

void motorInit();
void motorRun(bool fwd);
void motorStop();
uint8_t motorFaults();
void motorClearFaults();
void servoSet(uint32_t us);
void boostOn();
void boostOff();
void ledSet(uint8_t duty);
int batteryMv();
uint8_t batteryPct();
