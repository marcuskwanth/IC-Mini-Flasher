/*
Mini Flasher ESP32 Program - Version 250721.1
To do:
1. Add Bluetooth request data capability
*/

#include "esp_adc_cal.h"
#include <BluetoothSerial.h>  // Include Bluetooth Serial library
#include <Preferences.h>
#include <neotimer.h>
#include "esp_system.h"
#include "esp_sleep.h"  // Add deep sleep support
#include "driver/rtc_io.h"
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ====================================================================
// DEFINITIONS
// ====================================================================
// LCD Pin and Information Definition
#define I2C_SDA 21
#define I2C_SCL 22
#define LCD_ADDR 0x27
#define PAGE_TIME_MS 7000
constexpr uint8_t LCD_COLS = 16;
constexpr uint8_t LCD_ROWS = 2;

// GPIO + LED PWM Definition (change if necessary for your pins)
#define LED_FLA 27    // Mini-flasher indicator light (GREEN)
#define LED_BLE 2     // Bluetooth mode indicator light (BLUE)
#define LED_BATT 13   // Low battery indicator light (RED)

#define RED_PIN 25
#define GRN_PIN 26
#define BLUE_PIN 18
#define YEL_PIN 14   // ‘I’ in the CSV packet

#define LOW_BATT 36  // Battery Voltage ADC GPIO pin

#define POW_KEY 4    // Used as power on/off the device, active = LOW
#define MFB_KEY 17   // Used as switch mode + control mini flasher, active = LOW

#define OUTPUT_HIGH 19 // Set output to high to a pin when the a LED color is lit

constexpr uint8_t PWM_CH_RED = 0;
constexpr uint8_t PWM_CH_GRN = 1;
constexpr uint8_t PWM_CH_BLU = 2;
constexpr uint8_t PWM_CH_YEL = 3;
constexpr uint32_t PWM_FREQ = 5000;
constexpr uint8_t PWM_BITS = 8;  // intensity 0-255

// Timing Constants Definition
#define LONG_PRESS_TIME 2000     // Long press duration in milliseconds
#define SHORT_PRESS_TIME 200     // Short press duration in milliseconds
#define LED_ACTIVE_LOW 1         // Used if active is inverted (LOW = 1 / HIGH = 0) for the mini flasher light

// Payload packet limits
constexpr uint16_t PAYLOAD_MAX = 1002;
constexpr uint16_t PKT_MAX = PAYLOAD_MAX + 7;
constexpr uint8_t MAX_PAGES = 60;

// NVS namespace / keys
Preferences nvs;
const char *NS_LED = "led_pkt";
const char *KEY_LEN = "len";
const char *KEY_PAY = "pay";

// ====================================================================
// GLOABL OBJECTS
// ====================================================================
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);
Neotimer mytimer = Neotimer(100);  // Set timer interval in ms
BluetoothSerial SerialBT;

// ====================================================================
// GLOBAL BUFFERS
// ====================================================================
// Payload and Page Building
uint8_t payload[PAYLOAD_MAX];
uint16_t rxLen = 0;
uint16_t pktLen = 0;
uint16_t pktSum = 0;
uint16_t pktChk = 0;
uint8_t dataType = 0;
uint8_t COLOR_SEQ = 0x00;
uint8_t DATA_POLL = 0x01;
uint8_t DATA_REQU = 0x02;
char payStr[PAYLOAD_MAX + 1];
struct Page {
  char l1[LCD_COLS + 1];
  char l2[LCD_COLS + 1];
};
Page pages[MAX_PAGES];
uint8_t pageCnt = 1;
uint8_t pageIndex = 0;
uint32_t nextTurn = 0;
uint32_t TICK_MS = 100;

// Colour-sequence description
struct LedStep {
  char colour;    // 'R','G','B','I'
  uint8_t level;  // 0-255
  uint32_t onMs;  // milliseconds
  uint32_t offMs;
};
constexpr uint16_t MAX_STEPS = 250;
LedStep steps[MAX_STEPS];
uint16_t stepCount = 0;
uint32_t repeatCfg = 0;  // 0 = infinite
uint32_t repeatRemain = 0;

// Sequencer runtime state
bool seqEnabled = false;
uint16_t curStep = 0;
bool inOnTime = true;
uint32_t nextEvent = 0;

// boot lock-out timer (ignore key for 1.5 s)
constexpr uint32_t BOOT_LOCK_MS = 1500;
bool bootInputLocked = true;  // flag is “erect” at power-on
uint32_t bootUnlockAt = 0;    // timestamp when it drops

// Misc
int mode = 0;  // 0 = USB, 1 = BT
bool is_powered_on = false;
bool mini_flashing = false;
bool bt_waitingconnect = false;               // Bluetooth have initializated but waiting for connection.
bool just_powered_on = false;                 // Very important!
unsigned long Count100ms = 0;                 // 100ms counter from 0.

unsigned long pulseCurrTime = 0;
static uint32_t pulseEndTime = 0; // Tracks when to end the pulse

// ====================================================================
// FORWARD DECLARATIONS
// ====================================================================
// Packet and Page Building
bool receivePacket();
void buildPages();
void showPage(uint8_t idx);
void saveLatestLedPkt(const uint8_t *data, uint16_t len);
bool loadLatestLedPkt(uint8_t *data, uint16_t &len);
void sendStoredLedPkt();
void sendPollAck();

// Color and LEDs
void updateOutputHighPin();
void setAllLeds(uint8_t val);
void setColour(char c, uint8_t val);
void blinkLED();
void offLED();
void updateLEDs();
void checkMiniFlasher();

// LEDs Sequences
bool parseLedSequence(const uint8_t *buf, uint16_t len);
void startSequence();
void stopSequence();

// Button Handling
void handlePOW();
void handleMFB();
bool detectLongPress();

// Bluetooth Handling
void initializeBluetooth();
void toggleBluetoothConnection();

// Sleep (before and after) Handling
void enterDeepSleep();
void initialize();
void initLCD();
void powerDownLCD();
uint32_t readADC_Cal(int ADC_Raw);  // Battery-related

// ====================================================================
// FUNCTIONS
// ====================================================================
// Check if any LED is ON (PWM duty < 255)
void updateOutputHighPin() {
  bool anyOn = (ledcRead(PWM_CH_RED) < 255) || (ledcRead(PWM_CH_GRN) < 255) || (ledcRead(PWM_CH_BLU) < 255) || (ledcRead(PWM_CH_YEL) < 255);
  if (anyOn && pulseEndTime == 0) {
    digitalWrite(OUTPUT_HIGH, HIGH);
    pulseEndTime = millis() + 200; // Set end time (200ms from now)
  }
}
// Function to blink the LED briefly when the button is released in handleMFB()
void blinkLED() {
  digitalWrite(LED_BATT, LOW);
  delay(2);
  digitalWrite(LED_BATT, HIGH);
}
void offLED() {
  digitalWrite(LED_FLA, HIGH);
  digitalWrite(LED_BLE, HIGH);
  digitalWrite(LED_BATT, HIGH);
}
void updateLEDs() {
  digitalWrite(LED_BLE, mode == 1 ? LOW : HIGH);  // Blue on for BT, NONE for USB
}
void checkMiniFlasher() {
  digitalWrite(LED_FLA, mini_flashing ? LOW : HIGH);
}
static inline uint8_t mapLevel(uint8_t levelRaw) {
  if (LED_ACTIVE_LOW) return 255 - levelRaw;
  else return levelRaw;
}
void setAllLeds(uint8_t val) {  // COMMON-ANODE → invert
  uint8_t lvl = mapLevel(val);
  ledcWrite(PWM_CH_RED, lvl);
  ledcWrite(PWM_CH_GRN, lvl);
  ledcWrite(PWM_CH_BLU, lvl);
  ledcWrite(PWM_CH_YEL, lvl);
}
void setColour(char c, uint8_t val) {
  uint8_t lvl = mapLevel(val);
  switch (c) {
    case 'R': ledcWrite(PWM_CH_RED, lvl); break;
    case 'G': ledcWrite(PWM_CH_GRN, lvl); break;
    case 'B': ledcWrite(PWM_CH_BLU, lvl); break;
    case 'I': ledcWrite(PWM_CH_YEL, lvl); break;
  }
}
// LED-Sequence Related
bool parseLedSequence(const uint8_t *buf, uint16_t len) {
  stepCount = 0;
  repeatCfg = 0;

  char tmp[len + 1];
  memcpy(tmp, buf, len);
  tmp[len] = '\0';

  char *tok = strtok(tmp, ",");
  while (tok && stepCount < MAX_STEPS) {
    if (tok[0] == 'C') {  // repeat counter
      tok = strtok(nullptr, ",");
      repeatCfg = tok ? atoi(tok) : 0;
      break;
    }

    char colour = tok[0];
    tok = strtok(nullptr, ",");
    if (!tok) break;
    uint8_t lvl = atoi(tok);
    tok = strtok(nullptr, ",");
    if (!tok) break;
    uint16_t onS = atoi(tok);
    tok = strtok(nullptr, ",");
    if (!tok) break;
    uint16_t offS = atoi(tok);

    steps[stepCount++] = { colour, lvl, uint32_t(onS) * TICK_MS, uint32_t(offS) * TICK_MS };
    tok = strtok(nullptr, ",");
  }

  return (stepCount > 0);
}
void startSequence() {
  seqEnabled = true;
  mini_flashing = true;
  curStep = 0;
  inOnTime = true;
  repeatRemain = repeatCfg ? repeatCfg : 0xFFFFFFFF;  // infinite => large

  setAllLeds(0);
  delay(1);
  setColour(steps[0].colour, steps[0].level); 
  delay(1); updateOutputHighPin();

  nextEvent = millis() + steps[0].onMs;
}
void stopSequence() {
  seqEnabled = false;
  mini_flashing = false;
  setAllLeds(0);
}

// ====================================================================
// Packet-Related
void saveLatestLedPkt(const uint8_t *data, uint16_t len) {
  nvs.begin(NS_LED, false);
  nvs.putUInt(KEY_LEN, len);
  nvs.putBytes(KEY_PAY, data, len);
  nvs.end();
}
void sendPollAck() {
  uint32_t sum = 0;
  auto put = [&](uint8_t b) {
    Serial.write(b);
    sum += b;
  };

  put(0x5A);
  put(0xA5);
  put(0x00);
  put(0x00);
  put(DATA_POLL);

  uint16_t cs = sum & 0xFFFF;
  put(uint8_t(cs & 0xFF));
  put(uint8_t(cs >> 8));
}
bool loadLatestLedPkt(uint8_t *data, uint16_t &len) {
  nvs.begin(NS_LED, true);
  len = nvs.getUInt(KEY_LEN, 0);
  bool ok = (len && len <= PAYLOAD_MAX);
  if (ok) nvs.getBytes(KEY_PAY, data, len);
  nvs.end();
  return ok;
}
void sendStoredLedPkt() {
  uint16_t len;
  if (!loadLatestLedPkt(payload, len)) len = 0;

  uint32_t sum = 0;
  auto put = [&](uint8_t b) {
    if (mode == 0) Serial.write(b);
    else SerialBT.write(b);
    sum += b;
  };

  put(0x5A);
  put(0xA5);
  put(len & 0xFF);
  put(len >> 8);
  put(0x00);

  for (uint16_t i = 0; i < len; ++i) put(payload[i]);

  uint16_t cs = sum & 0xFFFF;
  put(uint8_t(cs & 0xFF));
  put(uint8_t(cs >> 8));
}

bool receivePacket() {
  enum { S1, S2, LEN1, LEN2, TYPE, PAY, CS1, CS2 };
  static uint8_t st = S1;
  static uint16_t len = 0, idx = 0, sum = 0;
  static uint8_t csLo = 0, csHi = 0;

  while (Serial.available() || SerialBT.available()) {
    blinkLED();
    uint8_t b = mode == 0 ? Serial.read() : SerialBT.read();
    switch (st) {
      case S1:
        if (b == 0x5A) { sum = b; st = S2; } break;
      case S2:
        if (b == 0xA5) { sum += b; st = LEN1; } else st = S1; break;
      case LEN1:
        len = b; sum += b; st = LEN2; break;
      case LEN2:
        len |= uint16_t(b) << 8; sum += b;
        if (len > PAYLOAD_MAX) { st = S1; break; }
        st = TYPE; break;
      case TYPE:
        dataType = b; sum += b; idx = 0; st = (len == 0) ? CS1 : PAY; break;
      case PAY: 
        payload[idx++] = b; sum += b;
        if (idx >= len) st = CS1; break;
      case CS1:
        csLo = b;
        if (b != uint8_t(sum & 0xFF)) { st = S1; break; }
        st = CS2; break;
      case CS2:
        csHi = b; if (b != uint8_t(sum >> 8)) { st = S1; break; }

      rxLen = len;
      pktLen = len + 7;
      pktSum = sum;
      pktChk = uint16_t(csHi) << 8 | csLo;

      if (dataType == DATA_POLL) {  // 0x01
        sendPollAck();
        st = S1;
        return false;
      }

      if (dataType == COLOR_SEQ) {
        saveLatestLedPkt(payload, rxLen);
        parseLedSequence(payload, rxLen);
        if (seqEnabled) {
          stopSequence();
        }
        startSequence();
      }

      if (dataType == DATA_REQU) {
        sendStoredLedPkt();
        st = S1;
        return true;
      }

      Serial.println("\nPacket OK.");
      st = S1;
      return true;
    }
  }
  return false;
}

// ====================================================================
// Append next CSV group
static void appendGroup(char *dst, char *&tok) {
  if (!tok) return;

  if (tok[0] == 'C') {
    char *cnt = (tok = strtok(nullptr, ","));
    snprintf(dst, LCD_COLS + 1, "C,%s", cnt ? cnt : "");
    tok = strtok(nullptr, ",");
    return;
  }

  char *t1 = tok;
  char *t2 = (tok = strtok(nullptr, ",")) ? tok : (char *)"";
  char *t3 = (tok = strtok(nullptr, ",")) ? tok : (char *)"";
  char *t4 = (tok = strtok(nullptr, ",")) ? tok : (char *)"";

  snprintf(dst, LCD_COLS + 1, "%s,%s,%s,%s,", t1, t2, t3, t4);
  tok = strtok(nullptr, ",");
}
// Format all pages
void buildPages() {
  if (dataType == COLOR_SEQ) snprintf(pages[0].l1, LCD_COLS + 1, "Received Seq.");
  else if (dataType == DATA_REQU) snprintf(pages[0].l1, LCD_COLS + 1, "Requesting Data");

  // Uncomment the following 2 codes for debug in the LCD
  // snprintf(pages[0].l1, LCD_COLS + 1, "Hdr:%04X Len:%u", 0x5AA5, rxLen);
  // snprintf(pages[0].l2, LCD_COLS + 1, "T:%02X", dataType);

  pageCnt = 1;
  if (dataType != COLOR_SEQ) return;

  memcpy(payStr, payload, rxLen);
  payStr[rxLen] = '\0';

  char *tok = strtok(payStr, ",");
  while (tok && pageCnt < MAX_PAGES) {
    pages[pageCnt].l1[0] = pages[pageCnt].l2[0] = '\0';
    appendGroup(pages[pageCnt].l1, tok);
    appendGroup(pages[pageCnt].l2, tok);
    ++pageCnt;
  }

  for (uint8_t i = pageCnt; i < MAX_PAGES; ++i)
    pages[i].l1[0] = pages[i].l2[0] = '\0';
}
void showPage(uint8_t idx) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(pages[idx].l1);
  lcd.setCursor(0, 1);
  lcd.print(pages[idx].l2);

  Serial.printf("LCD page %u / %u\n", idx, pageCnt - 1);
  Serial.printf("%s\n%s\n", pages[idx].l1, pages[idx].l2);
}

// ====================================================================
// Power on/off button
void handlePOW() {
  if (bootInputLocked) return;  // lock-out active? Ignore everything
  static unsigned long lastPressStart = millis();
  static bool isPressed = false;
  static bool longPressHandled = false;  // Track if long press was handled

  // Button pressed (active LOW)
  if (digitalRead(POW_KEY) == LOW) {
    if (!isPressed) {
      // New press detected
      lastPressStart = millis();
      isPressed = true;
      longPressHandled = false;  // Reset flag for new press
    }
    unsigned long pressDuration = millis() - lastPressStart;

    // CASE 3: Long press handling (> 2000ms)
    if (!just_powered_on) {
      if (pressDuration > LONG_PRESS_TIME && !longPressHandled) {
        Serial.println("*Very Long Press detected...");
        just_powered_on = false;

        // Implement power off logic here
        Serial.println("Powering off...");
        enterDeepSleep();
      }
    }
  }
  else {
    if (isPressed) { isPressed = false; just_powered_on = false; }
  }
}
// Handle MFB actions based on press duration after startup
void handleMFB() {
  static unsigned long lastPressStart = millis();
  static bool isPressed = false;
  static bool longPressHandled = false;  // Track if long press was handled

  // Button pressed (active LOW)
  if (digitalRead(MFB_KEY) == LOW) {
    if (!isPressed) {
      // New press detected
      lastPressStart = millis();
      isPressed = true;
      longPressHandled = false;  // Reset flag for new press
    }
    unsigned long pressDuration = millis() - lastPressStart;

    // CASE 2: Long press handling (>2000ms)
    if (pressDuration > LONG_PRESS_TIME && !longPressHandled) {
      Serial.println("*Long Press detected...");
      longPressHandled = true;  // Mark handled

      if (mode == 0) {  // USB mode
        toggleBluetoothConnection();
        Serial.println("USB -> Bluetooth");
      } 
      else {  // Bluetooth mode
        toggleBluetoothConnection();
        Serial.println("Bluetooth -> USB");
      }
    }
  }
  // Button released
  else {
    if (isPressed) {
      isPressed = false;  // Reset pressed state
      unsigned long pressDuration = millis() - lastPressStart;

      // CASE 1: Short press handling (200ms-2000ms)
      if (pressDuration > SHORT_PRESS_TIME && pressDuration < LONG_PRESS_TIME && !bt_waitingconnect) {
        Serial.println("*Short Press detected...");
        // blinkLED();
        mini_flashing = !mini_flashing;
        if (mini_flashing) {
          if (stepCount) {
            startSequence();
          }
        } 
        else {
          stopSequence();
        }
        Serial.println(mini_flashing ? "Mini-flasher ON" : "Mini-flasher OFF");
      }
    }
  }
}

// ====================================================================
// Function to initialize Bluetooth connection
void initializeBluetooth() {
  bt_waitingconnect = false;
  // Get the Bluetooth MAC address and set device name
  uint8_t btMac[6];
  if (esp_read_mac(btMac, ESP_MAC_BT) == ESP_OK) {
    Serial.print("Bluetooth MAC Address: ");
    for (int i = 0; i < 6; i++) {
      Serial.printf("%02X", btMac[i]);
      if (i < 5) Serial.print(":");
    }
    Serial.println();
  } else {
    Serial.println("Failed to read Bluetooth MAC address");
    while (1)
      ;  // Halt the program if fail to read BT MAC address.
  }

  // Set Bluetooth device name with last four digits of MAC address
  String deviceName = "ESP32_MiniFlasher";

  //The code initializes Bluetooth with a unique name based on the last four digits of the MAC address.
  if (!SerialBT.begin(deviceName.c_str())) {  // Set the Bluetooth name
    Serial.println("Bluetooth initialization failed!");
    while (1)
      ;  // Halt the program if Bluetooth fails to start
  }
  Serial.println("Bluetooth started with name: " + deviceName);
  Serial.println("Waiting for connection...");
  bt_waitingconnect = true;
}
// Function to toggle Bluetooth connection on/off based on button press
void toggleBluetoothConnection() {
  // Checking serial before doing anything else
  if (mode == 0) { 
    Serial.flush();
    Serial.end();
  }
  else {
    SerialBT.end();
    Serial.begin(115200);
    delay(50);
  }

  // Performing actual toggling
  if (mode == 0) {
    if (!bt_waitingconnect) {  // if BT is not connected and waiting for connection, exit with no action.
      mode = 1;
      initializeBluetooth();
      bt_waitingconnect = true;
      Serial.println("BT is turned ON.");
    }
  } 
  else {  // mode == 1
    mode = 0;
    bt_waitingconnect = false;
    digitalWrite(LED_BLE, HIGH);  // Turn off Blue LED.
    Serial.println("BT is turned OFF.");
  }
}

// ====================================================================
// Sleep handling
void enterDeepSleep() {
  Serial.println("Entering deep sleep...");

  // Clean up before sleep
  stopSequence();  // Ensure LEDs are off
  powerDownLCD();
  SerialBT.end();
  offLED();
  Serial.flush();
  delay(10);

  // Wait for key release
  while (digitalRead(MFB_KEY) == LOW)  // key still held ?
    delay(10);

  // Lock-out interval
  const uint32_t LOCK_MS = 2000;
  uint32_t t0 = millis();
  while (millis() - t0 < LOCK_MS)
    delay(10);

  // Arm the wake-up source and sleep
  esp_sleep_enable_ext0_wakeup((gpio_num_t)MFB_KEY, 0);  // active-LOW
  rtc_gpio_isolate((gpio_num_t)MFB_KEY);                 // save a few µA
  Serial.println("…now really sleeping");
  delay(20);  // pending UART
  esp_deep_sleep_start();
}

// LCD init and shut down
void initLCD() {
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.begin();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Device Ready");
  lcd.setCursor(0, 1);
}
void powerDownLCD() {
  lcd.clear();
  lcd.noBacklight();
  lcd.noDisplay();
  delay(50);
  Wire.end();

  // Set I2C pins to input mode to reduce power
  pinMode(I2C_SDA, INPUT);
  pinMode(I2C_SCL, INPUT);
}

// ====================================================================
// Used for battery voltage
uint32_t readADC_Cal(int ADC_Raw) {
  esp_adc_cal_characteristics_t adc_chars;
  esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_WIDTH_BIT_12, 1100, &adc_chars);
  return (esp_adc_cal_raw_to_voltage(ADC_Raw, &adc_chars));
}

/* ----------------------------------------------------------------- */
/* SETUP */
/* ----------------------------------------------------------------- */
void setup() {
  // ESP Sleep
  esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
  esp_sleep_enable_ext0_wakeup((gpio_num_t)POW_KEY, 0);                   // Config wake-up source
  esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();

  pinMode(POW_KEY, INPUT_PULLUP);   // POW_KEY is active LOW
  // "Fake" Power on to check if the power button is pressed for 2 seconds
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT0) {
    unsigned long wakeTime = millis();
    while (digitalRead(POW_KEY) == LOW) {
      if (millis() - wakeTime >= LONG_PRESS_TIME) break;
      delay(10);
    }
    if (millis() - wakeTime < LONG_PRESS_TIME) {
      esp_deep_sleep_start();  // Back to sleep
    }
  }

  // Startup after checking power button
  Serial.begin(115200);
  delay(50);

  // PWM LED Setup
  ledcSetup(PWM_CH_RED, PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_GRN, PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_BLU, PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_YEL, PWM_FREQ, PWM_BITS);
  ledcAttachPin(RED_PIN, PWM_CH_RED);
  ledcAttachPin(GRN_PIN, PWM_CH_GRN);
  ledcAttachPin(BLUE_PIN, PWM_CH_BLU);
  ledcAttachPin(YEL_PIN, PWM_CH_YEL);
  setAllLeds(0);  // Turn off PWM LEDs
  initLCD();

  // Pins init
  pinMode(MFB_KEY, INPUT_PULLUP);   // MFB_KEY is active LOW
  pinMode(LOW_BATT, INPUT);  // LOW_BATT analog input (FIXED)
  pinMode(LED_FLA, OUTPUT);
  pinMode(LED_BLE, OUTPUT);
  pinMode(LED_BATT, OUTPUT);
  pinMode(OUTPUT_HIGH, OUTPUT);
  digitalWrite(OUTPUT_HIGH, LOW);
  offLED();  // Turn all LEDs off

  // Load stored LED sequence
  uint16_t lenBoot;
  if (loadLatestLedPkt(payload, lenBoot)) {
    parseLedSequence(payload, lenBoot);
  }
  // If wake from sleep
  if (wakeup_reason == ESP_SLEEP_WAKEUP_EXT0) {
    Serial.println("Woke from deep sleep");
    //lcd.print("Waked Up");
    if (digitalRead(POW_KEY) == LOW) just_powered_on = true;
  }
  // If normal boot
  else {
    Serial.println("Woke from Normal boot");
    //lcd.print("Booted Up");
  }
  bootInputLocked = true;
  bootUnlockAt = millis() + BOOT_LOCK_MS; // Arm the boot lock-out timer
  mytimer.start();  // Start the timer
}

/* ----------------------------------------------------------------- */
/* LOOP */
/* ----------------------------------------------------------------- */
void loop() {
  // Drop the lock flag when time expired
  if (bootInputLocked && (int32_t)(millis() - bootUnlockAt) >= 0)
    bootInputLocked = false;

  /* 1. UART packet handling */
  if (receivePacket()) {
    buildPages();
    pageIndex = 0;
    showPage(pageIndex);
    nextTurn = millis() + PAGE_TIME_MS;
    if (dataType == COLOR_SEQ)  // new LED sequence arrived
      parseLedSequence(payload, rxLen);
  }

  /* 2. LCD page rotation (debugging)*/
  /*
  if (pktLen && (int32_t)(millis() - nextTurn) >= 0) {
    pageIndex = (pageIndex + 1) % pageCnt;
    showPage(pageIndex);
    nextTurn += PAGE_TIME_MS;
  }
  */

  /* 3. Sequencer state machine (ADDED) */
  if (seqEnabled && (int32_t)(millis() - nextEvent) >= 0) {
    if (inOnTime) {
      setAllLeds(0);
      inOnTime = false;
      nextEvent += steps[curStep].offMs;
    } 
    else {
      /* move to next step */
      inOnTime = true;
      curStep++;
      if (curStep >= stepCount) {
        /* list finished */
        if (repeatCfg == 0) {  // infinite
          curStep = 0;
        } 
        else {
          if (repeatRemain > 1) {
            repeatRemain--;
            curStep = 0;
          } 
          else {  // done
            stopSequence();
          }
        }
      }
      delay(1);
      setColour(steps[curStep].colour, steps[curStep].level);
      delay(1); updateOutputHighPin();

      nextEvent = millis() + steps[curStep].onMs;
    }
  }

  /* 4. Handle pulse timeout */
  if (pulseEndTime != 0 && millis() >= pulseEndTime) {
    digitalWrite(OUTPUT_HIGH, LOW);
    pulseEndTime = 0; // Reset
  }

  /* 5. Timer interrupt for battery logging, button presses, BT/USB detection */
  if (mytimer.repeat()) {

    // Battery logger
    int rawValue = analogRead(LOW_BATT);
    float voltage = float(readADC_Cal(rawValue)) / 1000 * 2;
    float voltage_old = (float)rawValue / 4095 * 2 * 3.8;
    lcd.setCursor(0, 1);
    lcd.print("Voltage: "); lcd.print(voltage);

    // Check MFB and POW state and perform actions accordingly after powering on!!
    handleMFB();
    handlePOW();
    checkMiniFlasher();

    // Check if Bluetooth is connected
    if (mode == 1) {
      if (!SerialBT.hasClient()) {
        stopSequence();
        bt_waitingconnect = true;
      }
    }

    // What if Bluetooth not connected?
    if (bt_waitingconnect) {  // if bt_connected=false and BT wait for connect, toggle BLUE LED.
      digitalWrite(LED_BATT, HIGH);
      static uint32_t lastBTBlinkTime = 0;
      if (millis() - lastBTBlinkTime >= 1000) { // 1 second interval
        digitalWrite(LED_BLE, !digitalRead(LED_BLE));
        lastBTBlinkTime = millis();
      }
    }
    else {
      updateLEDs();
    }

    // Check if Bluetooth is reconnected
    if (bt_waitingconnect) {
      if (SerialBT.hasClient()) {
        offLED();
        digitalWrite(LED_BLE, LOW);
        Serial.println("Connected via BT! ESP32 is ready to send data after disconnected.");
        mode = 1;
        bt_waitingconnect = false;
      }
    }

    // Low battery light flashing
    if (voltage <= 3.5) {  // LOW_BATT is active low.
      digitalWrite(LED_BLE, HIGH);
      static uint32_t lastBattBlinkTime = 0;
      if (millis() - lastBattBlinkTime >= 1000) { // 1 second interval
        digitalWrite(LED_BATT, !digitalRead(LED_BATT));
        lastBattBlinkTime = millis();
      }
    } 
    else {
      if (!bt_waitingconnect) {
        digitalWrite(LED_BATT, HIGH);
        updateLEDs();
      }
    }

    // Increment counter
    Count100ms++;
    if (Count100ms == 100) {
      Count100ms = 0;
    }
  }
}