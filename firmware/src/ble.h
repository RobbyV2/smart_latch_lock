#pragma once
#include <stdint.h>

void bleInit();
void bleNotifyState(uint8_t s, uint8_t f);
bool blePairing();
void bleClearBonds();
