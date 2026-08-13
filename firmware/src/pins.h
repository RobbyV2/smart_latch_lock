#pragma once
#include <stdint.h>

constexpr int PIN_VBAT_SENSE = 0;
constexpr int PIN_IPROPI = 1;
constexpr int PIN_NFAULT = 2;
constexpr int PIN_SW_LATCH = 3;
constexpr int PIN_SW_OPEN = 4;
constexpr int PIN_SW_CLOSED = 5;
constexpr int PIN_MOTOR_EN = 6;
constexpr int PIN_MOTOR_PH = 7;
constexpr int PIN_LED = 8;
constexpr int PIN_BUTTON = 9;
constexpr int PIN_SERVO = 10;
constexpr int PIN_DRV_NSLEEP = 20;
constexpr int PIN_BOOST_EN = 21;

constexpr uint32_t INRUSH_MASK_US = 120000;
constexpr uint32_t MOTOR_TIMEOUT_MS = 3000;
constexpr uint32_t LATCH_TIMEOUT_MS = 500;
constexpr uint32_t UNLATCH_TIMEOUT_MS = 300;
constexpr uint32_t BTN_HOLD_MS = 3000;
constexpr uint32_t BOND_CLEAR_HOLD_MS = 10000;
constexpr int SOFT_STALL_MV = 1200;
constexpr int SOFT_STALL_SAMPLES = 20;
constexpr int VBAT_MIN_LOCK_MV = 3300;
constexpr uint32_t SERVO_RETRACT_US = 1000;
constexpr uint32_t SERVO_RELEASE_US = 2000;
constexpr uint32_t BLE_PASSKEY = 835271;

constexpr char UUID_SVC[] = "8f1d0001-2f3a-4c6e-9b1d-6a0f5e3c7a42";
constexpr char UUID_CMD[] = "8f1d0002-2f3a-4c6e-9b1d-6a0f5e3c7a42";
constexpr char UUID_STATE[] = "8f1d0003-2f3a-4c6e-9b1d-6a0f5e3c7a42";

enum class State : uint8_t {
  UnlockedOpen, Closing, Seating, Locked, Unlatching, Opening, FaultObstructed, FaultTimeout
};
enum class Event : uint8_t {
  CmdLock, CmdUnlock, CmdClear, BtnShort, BtnHold3, EsClosed, EsOpen,
  LatchSeated, LatchClear, Stall, Timeout, Raw
};

constexpr uint8_t F_STALL_HW = 0x01, F_STALL_SOFT = 0x02, F_TIMEOUT = 0x04, F_LATCH = 0x08, F_LOWBAT = 0x10;
