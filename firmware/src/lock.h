#pragma once
#include "pins.h"

void lockInit();
void lockPost(Event ev);
void lockPostFromISR(Event ev);
