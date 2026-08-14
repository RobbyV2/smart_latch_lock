#include <Arduino.h>
#include <string.h>
#include <driver/gpio.h>
#include <driver/ledc.h>
#include <esp_adc/adc_oneshot.h>
#include <esp_adc/adc_cali.h>
#include <esp_adc/adc_cali_scheme.h>
#include <esp_timer.h>
#include <esp_rom_gpio.h>
#include <soc/gpio_reg.h>
#include <soc/gpio_sig_map.h>
#include <soc/ledc_periph.h>
#include "pins.h"
#include "motor.h"
#include "lock.h"

static constexpr ledc_channel_t CH_MOTOR = LEDC_CHANNEL_0, CH_SERVO = LEDC_CHANNEL_1, CH_LED = LEDC_CHANNEL_2;
static adc_oneshot_unit_handle_t adc;
static adc_cali_handle_t cali;
static esp_timer_handle_t maskTimer, sampleTimer;
static volatile uint8_t faults;
static int win[8], wi, wsum, softCnt;
static bool boost;
static int64_t boostOffAt;
static volatile bool running;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR killPwm() {
  REG_WRITE(GPIO_FUNC0_OUT_SEL_CFG_REG + 4 * PIN_MOTOR_EN, SIG_GPIO_OUT_IDX);
  REG_WRITE(GPIO_OUT_W1TC_REG, 1u << PIN_MOTOR_EN);
}

static void IRAM_ATTR faultIsr(void*) {
  killPwm();
  faults |= F_STALL_HW;
  lockPostFromISR(Event::Stall);
}

static void maskCb(void*) {
  portENTER_CRITICAL(&mux);
  bool r = running && !esp_timer_is_active(maskTimer);
  if (r) {
    REG_WRITE(GPIO_STATUS_W1TC_REG, 1u << PIN_NFAULT);
    gpio_intr_enable((gpio_num_t)PIN_NFAULT);
  }
  portEXIT_CRITICAL(&mux);
  if (r) esp_timer_start_periodic(sampleTimer, 1000);
}

static int adcMv(adc_channel_t ch) {
  int raw = 0, mv = 0;
  adc_oneshot_read(adc, ch, &raw);
  adc_cali_raw_to_voltage(cali, raw, &mv);
  return mv;
}

static void sampleCb(void*) {
  int mv = adcMv(ADC_CHANNEL_1);
  wsum += mv - win[wi];
  win[wi] = mv;
  wi = (wi + 1) & 7;
  if (wsum / 8 > SOFT_STALL_MV) {
    if (++softCnt >= SOFT_STALL_SAMPLES) {
      killPwm();
      esp_timer_stop(sampleTimer);
      faults |= F_STALL_SOFT;
      lockPost(Event::Stall);
    }
  } else {
    softCnt = 0;
  }
}

static void ledcCh(ledc_channel_t ch, ledc_timer_t t, int pin, bool invert) {
  ledc_channel_config_t c = {};
  c.gpio_num = pin;
  c.speed_mode = LEDC_LOW_SPEED_MODE;
  c.channel = ch;
  c.timer_sel = t;
  c.duty = 0;
  c.flags.output_invert = invert;
  ledc_channel_config(&c);
}

void motorInit() {
  gpio_config_t out = {};
  out.pin_bit_mask = BIT64(PIN_MOTOR_PH) | BIT64(PIN_BOOST_EN);
  out.mode = GPIO_MODE_OUTPUT;
  gpio_config(&out);
  out.pin_bit_mask = BIT64(PIN_VBUS_DET);
  out.mode = GPIO_MODE_INPUT;
  gpio_config(&out);

  ledc_timer_config_t t = {};
  t.speed_mode = LEDC_LOW_SPEED_MODE;
  t.clk_cfg = LEDC_AUTO_CLK;
  t.timer_num = LEDC_TIMER_0;
  t.duty_resolution = LEDC_TIMER_10_BIT;
  t.freq_hz = 20000;
  ledc_timer_config(&t);
  t.timer_num = LEDC_TIMER_1;
  t.duty_resolution = LEDC_TIMER_14_BIT;
  t.freq_hz = 50;
  ledc_timer_config(&t);
  t.timer_num = LEDC_TIMER_2;
  t.duty_resolution = LEDC_TIMER_8_BIT;
  t.freq_hz = 5000;
  ledc_timer_config(&t);
  ledcCh(CH_MOTOR, LEDC_TIMER_0, PIN_MOTOR_EN, false);
  ledcCh(CH_SERVO, LEDC_TIMER_1, PIN_SERVO, false);
  ledcCh(CH_LED, LEDC_TIMER_2, PIN_LED, true);

  adc_oneshot_unit_init_cfg_t u = {};
  u.unit_id = ADC_UNIT_1;
  adc_oneshot_new_unit(&u, &adc);
  adc_oneshot_chan_cfg_t cc = {};
  cc.atten = ADC_ATTEN_DB_12;
  cc.bitwidth = ADC_BITWIDTH_DEFAULT;
  adc_oneshot_config_channel(adc, ADC_CHANNEL_0, &cc);
  adc_oneshot_config_channel(adc, ADC_CHANNEL_1, &cc);
  adc_cali_curve_fitting_config_t cf = {};
  cf.unit_id = ADC_UNIT_1;
  cf.atten = ADC_ATTEN_DB_12;
  cf.bitwidth = ADC_BITWIDTH_DEFAULT;
  adc_cali_create_scheme_curve_fitting(&cf, &cali);

  gpio_config_t in = {};
  in.pin_bit_mask = BIT64(PIN_NFAULT);
  in.mode = GPIO_MODE_INPUT;
  in.intr_type = GPIO_INTR_NEGEDGE;
  gpio_config(&in);
  gpio_isr_handler_add((gpio_num_t)PIN_NFAULT, faultIsr, nullptr);
  gpio_intr_disable((gpio_num_t)PIN_NFAULT);

  esp_timer_create_args_t a = {};
  a.callback = maskCb;
  a.name = "mask";
  esp_timer_create(&a, &maskTimer);
  a.callback = sampleCb;
  a.name = "ipropi";
  esp_timer_create(&a, &sampleTimer);
}

void motorRun(bool fwd) {
  setCpuFrequencyMhz(160);
  gpio_set_level((gpio_num_t)PIN_MOTOR_PH, fwd);
  memset(win, 0, sizeof win);
  wi = wsum = softCnt = 0;
  esp_timer_stop(maskTimer);
  esp_timer_stop(sampleTimer);
  portENTER_CRITICAL(&mux);
  running = true;
  gpio_intr_disable((gpio_num_t)PIN_NFAULT);
  esp_timer_start_once(maskTimer, INRUSH_MASK_US);
  portEXIT_CRITICAL(&mux);
  esp_rom_gpio_connect_out_signal(PIN_MOTOR_EN, ledc_periph_signal[0].sig_out0_idx + CH_MOTOR, false, false);
  ledc_set_duty(LEDC_LOW_SPEED_MODE, CH_MOTOR, 1 << 10);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, CH_MOTOR);
}

void motorStop() {
  esp_timer_stop(maskTimer);
  esp_timer_stop(sampleTimer);
  portENTER_CRITICAL(&mux);
  running = false;
  gpio_intr_disable((gpio_num_t)PIN_NFAULT);
  REG_WRITE(GPIO_STATUS_W1TC_REG, 1u << PIN_NFAULT);
  portEXIT_CRITICAL(&mux);
  ledc_set_duty(LEDC_LOW_SPEED_MODE, CH_MOTOR, 0);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, CH_MOTOR);
  killPwm();
  setCpuFrequencyMhz(80);
}

uint8_t motorFaults() { return faults; }
void motorClearFaults() { faults = 0; }

void servoSet(uint32_t us) {
  ledc_set_duty(LEDC_LOW_SPEED_MODE, CH_SERVO, us * 16384 / 20000);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, CH_SERVO);
}

void boostOn() {
  if (boost) return;
  int64_t off = esp_timer_get_time() / 1000 - boostOffAt;
  if (off < BOOST_OFF_MS) vTaskDelay(pdMS_TO_TICKS(BOOST_OFF_MS - off));
  gpio_set_level((gpio_num_t)PIN_BOOST_EN, 1);
  vTaskDelay(pdMS_TO_TICKS(20));
  boost = true;
}

void boostOff() {
  ledc_set_duty(LEDC_LOW_SPEED_MODE, CH_SERVO, 0);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, CH_SERVO);
  gpio_set_level((gpio_num_t)PIN_BOOST_EN, 0);
  boost = false;
  boostOffAt = esp_timer_get_time() / 1000;
}

bool vbusPresent() { return gpio_get_level((gpio_num_t)PIN_VBUS_DET); }

void ledSet(uint8_t duty) {
  ledc_set_duty(LEDC_LOW_SPEED_MODE, CH_LED, duty);
  ledc_update_duty(LEDC_LOW_SPEED_MODE, CH_LED);
}

int batteryMv() {
  int s = 0;
  for (int i = 0; i < 16; i++) s += adcMv(ADC_CHANNEL_0);
  return s * 2 / 16;
}

uint8_t batteryPct() {
  int p = (batteryMv() - 3300) * 100 / 900;
  return (uint8_t)(p < 0 ? 0 : p > 100 ? 100 : p);
}
