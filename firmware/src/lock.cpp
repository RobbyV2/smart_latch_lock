#include <Arduino.h>
#include <driver/gpio.h>
#include <esp_timer.h>
#include "pins.h"
#include "lock.h"
#include "motor.h"
#include "ble.h"

struct Msg {
  Event ev;
  uint8_t pin;
};

static QueueHandle_t q;
static esp_timer_handle_t ledTimer;
static State st;
static uint8_t faults;
static bool retreat, btnDown;
static uint8_t seatTries;
static int64_t stateDl, btnDl;

static int64_t nowMs() { return esp_timer_get_time() / 1000; }
static bool made(int pin) { return !gpio_get_level((gpio_num_t)pin); }

void lockPost(Event ev) {
  if (!q) return;
  Msg m{ev, 0};
  xQueueSend(q, &m, 0);
}

void IRAM_ATTR lockPostFromISR(Event ev) {
  if (!q) return;
  Msg m{ev, 0};
  BaseType_t w = pdFALSE;
  xQueueSendFromISR(q, &m, &w);
  portYIELD_FROM_ISR(w);
}

static void IRAM_ATTR pinIsr(void* arg) {
  Msg m{Event::Raw, (uint8_t)(uintptr_t)arg};
  BaseType_t w = pdFALSE;
  xQueueSendFromISR(q, &m, &w);
  portYIELD_FROM_ISR(w);
}

static void startOpening(bool r) {
  retreat = r;
  boostOn();
  servoSet(SERVO_RETRACT_US);
  motorRun(false);
  st = State::Opening;
  stateDl = nowMs() + MOTOR_TIMEOUT_MS;
}

static void startClosing() {
  faults = 0;
  motorClearFaults();
  boostOn();
  servoSet(SERVO_RETRACT_US);
  motorRun(true);
  st = State::Closing;
  stateDl = nowMs() + MOTOR_TIMEOUT_MS;
}

static void enterUnlatching() {
  boostOn();
  servoSet(SERVO_RETRACT_US);
  st = State::Unlatching;
  stateDl = nowMs() + UNLATCH_TIMEOUT_MS;
  if (!made(PIN_SW_LATCH)) startOpening(false);
}

static void derive() {
  faults = 0;
  motorClearFaults();
  stateDl = 0;
  bool closed = made(PIN_SW_CLOSED), open = made(PIN_SW_OPEN), seated = made(PIN_SW_LATCH);
  if (closed && seated) {
    st = State::Locked;
    boostOff();
  } else if (seated) {
    st = State::FaultObstructed;
    faults |= F_LATCH;
    boostOff();
  } else if (open && !closed) {
    st = State::UnlockedOpen;
    boostOff();
  } else {
    startOpening(true);
  }
}

static void handle(Event ev) {
  if (ev == Event::Stall) faults |= motorFaults();
  switch (st) {
    case State::UnlockedOpen:
      if (ev == Event::CmdLock || ev == Event::BtnShort) {
        faults &= ~F_LOWBAT;
        if (batteryMv() < VBAT_MIN_LOCK_MV) {
          faults |= F_LOWBAT;
          break;
        }
        startClosing();
      }
      break;
    case State::Closing:
      switch (ev) {
        case Event::EsClosed:
          motorStop();
          servoSet(SERVO_RELEASE_US);
          seatTries = 0;
          st = State::Seating;
          stateDl = nowMs() + LATCH_TIMEOUT_MS;
          break;
        case Event::Stall:
        case Event::Timeout:
          motorStop();
          if (ev == Event::Timeout) faults |= F_TIMEOUT;
          startOpening(true);
          break;
        case Event::BtnHold3:
          motorStop();
          enterUnlatching();
          break;
        default:
          break;
      }
      break;
    case State::Seating:
      switch (ev) {
        case Event::LatchSeated:
          if (made(PIN_SW_CLOSED)) {
            st = State::Locked;
            stateDl = 0;
            boostOff();
          }
          break;
        case Event::Timeout:
          if (seatTries++ == 0) {
            servoSet(SERVO_RETRACT_US);
            vTaskDelay(pdMS_TO_TICKS(150));
            servoSet(SERVO_RELEASE_US);
            stateDl = nowMs() + LATCH_TIMEOUT_MS;
          } else {
            faults |= F_LATCH;
            servoSet(SERVO_RETRACT_US);
            startOpening(true);
          }
          break;
        case Event::BtnHold3:
          enterUnlatching();
          break;
        default:
          break;
      }
      break;
    case State::Locked:
      if (ev == Event::CmdUnlock || ev == Event::BtnShort || ev == Event::BtnHold3) enterUnlatching();
      else if (ev == Event::LatchClear) derive();
      break;
    case State::Unlatching:
      switch (ev) {
        case Event::LatchClear:
          startOpening(false);
          break;
        case Event::Timeout:
          servoSet(SERVO_RELEASE_US);
          boostOff();
          faults |= F_TIMEOUT;
          st = State::FaultTimeout;
          break;
        default:
          break;
      }
      break;
    case State::Opening:
      switch (ev) {
        case Event::EsOpen:
          motorStop();
          servoSet(SERVO_RELEASE_US);
          boostOff();
          retreat = false;
          stateDl = 0;
          st = State::UnlockedOpen;
          break;
        case Event::Stall:
          motorStop();
          boostOff();
          stateDl = 0;
          st = State::FaultObstructed;
          break;
        case Event::Timeout:
          motorStop();
          boostOff();
          faults |= F_TIMEOUT;
          st = State::FaultTimeout;
          break;
        default:
          break;
      }
      break;
    case State::FaultObstructed:
    case State::FaultTimeout:
      if (ev == Event::CmdClear) derive();
      else if (ev == Event::BtnHold3) enterUnlatching();
      break;
  }
}

static void apply(Event ev) {
  State old = st;
  uint8_t of = faults;
  handle(ev);
  if (st != old || faults != of) bleNotifyState((uint8_t)st, faults);
}

static void debounce(uint8_t pin) {
  vTaskDelay(pdMS_TO_TICKS(pin == PIN_BUTTON ? 25 : 15));
  bool m = made(pin);
  switch (pin) {
    case PIN_SW_CLOSED:
      if (m) apply(Event::EsClosed);
      break;
    case PIN_SW_OPEN:
      if (m) apply(Event::EsOpen);
      break;
    case PIN_SW_LATCH:
      apply(m ? Event::LatchSeated : Event::LatchClear);
      break;
    case PIN_BUTTON:
      if (m && !btnDown) {
        btnDown = true;
        btnDl = nowMs() + BTN_HOLD_MS;
      } else if (!m && btnDown) {
        btnDown = false;
        if (btnDl) apply(Event::BtnShort);
        btnDl = 0;
      }
      break;
  }
}

static void ledCb(void*) {
  static uint32_t t;
  t++;
  if (blePairing()) {
    uint32_t p = t % 40;
    ledSet((uint8_t)((p < 20 ? p : 40 - p) * 12));
    return;
  }
  bool on;
  switch (st) {
    case State::UnlockedOpen:
      on = t % 60 < 2;
      break;
    case State::Locked: {
      uint32_t p = t % 100;
      on = p < 2 || (p >= 4 && p < 6);
      break;
    }
    case State::FaultObstructed:
    case State::FaultTimeout:
      on = t & 1;
      break;
    default:
      on = t % 4 < 2;
      break;
  }
  ledSet(on ? 255 : 0);
}

static void task(void*) {
  bleNotifyState((uint8_t)st, faults);
  for (;;) {
    int64_t t = nowMs(), next = INT64_MAX;
    if (stateDl) next = stateDl;
    if (btnDown && btnDl && btnDl < next) next = btnDl;
    TickType_t to = next == INT64_MAX ? portMAX_DELAY : pdMS_TO_TICKS(next > t ? next - t : 0);
    Msg m;
    if (xQueueReceive(q, &m, to) == pdTRUE) {
      if (m.ev == Event::Raw) debounce(m.pin);
      else apply(m.ev);
    } else {
      t = nowMs();
      if (btnDown && btnDl && t >= btnDl) {
        btnDl = 0;
        apply(Event::BtnHold3);
      } else if (stateDl && t >= stateDl) {
        stateDl = 0;
        apply(Event::Timeout);
      }
    }
  }
}

void lockInit() {
  q = xQueueCreate(16, sizeof(Msg));
  gpio_config_t in = {};
  in.pin_bit_mask = BIT64(PIN_SW_LATCH) | BIT64(PIN_SW_OPEN) | BIT64(PIN_SW_CLOSED) | BIT64(PIN_BUTTON);
  in.mode = GPIO_MODE_INPUT;
  in.pull_up_en = GPIO_PULLUP_ENABLE;
  in.intr_type = GPIO_INTR_ANYEDGE;
  gpio_config(&in);
  for (int p : {PIN_SW_LATCH, PIN_SW_OPEN, PIN_SW_CLOSED, PIN_BUTTON})
    gpio_isr_handler_add((gpio_num_t)p, pinIsr, (void*)(uintptr_t)p);
  derive();
  esp_timer_create_args_t a = {};
  a.callback = ledCb;
  a.name = "led";
  esp_timer_create(&a, &ledTimer);
  esp_timer_start_periodic(ledTimer, 50000);
  xTaskCreate(task, "lock", 4096, nullptr, 5, nullptr);
}
