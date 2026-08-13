#pragma once
#include <stdint.h>
#include <string>

void bleInit();
void bleNotifyState(uint8_t s, uint8_t f);
bool bleMasterStored();
bool bleMasterPresent();
bool bleAdoptArmed();
void bleAdoptToggle();
void bleMasterDelete();
std::string bleMasterAddr();
