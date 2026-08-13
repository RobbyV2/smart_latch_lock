#pragma once
#include "pins.h"

void lockInit();
void lockPost(Event ev);
void lockPostFromISR(Event ev);
uint8_t lockState();
uint8_t lockFaults();
