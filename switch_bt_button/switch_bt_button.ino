/*
NOTE: This file is just used for testing!
For complete version, please look at ESP32_INO instead!
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
// LED and LCD Pin Definition (usually GPIO 2 for the built-in LED)
#define I2C_SDA       21
#define I2C_SCL       22
#define LCD_ADDR      0x27
#define PAGE_TIME_MS  7000
constexpr uint8_t  LCD_COLS     = 16;
constexpr uint8_t  LCD_ROWS     = 2;

// GPIO + LED PWM Definition
#define LED_USB   27
#define LED_BLE   2
#define LED_STA   13

#define RED_PIN   25
#define GRN_PIN   14
#define BLUE_PIN  12
#define YEL_PIN   26  // ‘I’ in the CSV
#define LOW_BATT  13  // Low battery ADC GPIO pin
#define MFB_KEY   4   // Need to set to input+internal_pullup, active = LOW

constexpr uint8_t  PWM_CH_RED  = 0;
constexpr uint8_t  PWM_CH_GRN  = 1;
constexpr uint8_t  PWM_CH_BLU  = 2;
constexpr uint8_t  PWM_CH_YEL  = 3;
constexpr uint32_t PWM_FREQ    = 5000;
constexpr uint8_t  PWM_BITS    = 8;    // intensity 0-255

// Timing Constants Definition
#define VERY_LONG_PRESS_TIME  3000  // Very Long press duration in milliseconds
#define LONG_PRESS_TIME       2000  // Long press duration in milliseconds
#define SHORT_PRESS_TIME      200   // Short press duration in milliseconds

// Payload packet limits
constexpr uint16_t PAYLOAD_MAX  = 1002;
constexpr uint16_t PKT_MAX      = PAYLOAD_MAX + 7;
constexpr uint8_t  MAX_PAGES    = 60;

// NVS namespace / keys
Preferences nvs;
const char *NS_LED  = "led_pkt";
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
uint8_t  payload[PAYLOAD_MAX];
uint16_t rxLen  = 0;
uint16_t pktLen = 0;
uint16_t pktSum = 0;
uint16_t pktChk = 0;
uint8_t  dataType = 0;
uint8_t  DATA_POLL = 0x01;
char     payStr[PAYLOAD_MAX + 1];
struct   Page { char l1[LCD_COLS + 1]; char l2[LCD_COLS + 1]; };
Page     pages[MAX_PAGES];
uint8_t  pageCnt   = 1;
uint8_t  pageIndex = 0;
uint32_t nextTurn  = 0;
uint32_t TICK_MS = 100;  

// Colour-sequence description
struct LedStep {
  char     colour;   // 'R','G','B','I'
  uint8_t  level;    // 0-255
  uint32_t onMs;     // milliseconds
  uint32_t offMs;
};
constexpr uint16_t MAX_STEPS = 250;
LedStep steps[MAX_STEPS];
uint16_t stepCount     = 0;
uint32_t repeatCfg     = 0;    // 0 = infinite
uint32_t repeatRemain  = 0;

// Sequencer runtime state
bool     seqEnabled = false;
uint16_t curStep    = 0;
bool     inOnTime   = true;
uint32_t nextEvent  = 0;

// Misc
int  mode = 0;                               // 0 = BT, 1 = USB
bool is_powered_on = false;
bool mini_flashing = false;
bool bt_waitingconnect = false;              // Bluetooth have initializated but waiting for connection.
bool just_switched_from_btp_to_usb = false;  // Very important!
unsigned long Count100ms = 0;                // 100ms counter from 0.

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
void setAllLeds(uint8_t val);
void setColour(char c, uint8_t val);
void blinkLED();
void offLED();
void updateLEDs();

// LEDs Sequences
bool parseLedSequence(const uint8_t *buf, uint16_t len);
void startSequence();
void stopSequence();

// Button Handling
void handleMFB();
bool detectLongPress();

// Bluetooth Handling
void initializeBluetooth()
void toggleBluetoothConnection();

// Sleep (before and after) Handling
void enterDeepSleep();
void initialize();
void initLCD();
void powerDownLCD();
uint32_t readADC_Cal(int ADC_Raw)   // Battery-related

void enterDeepSleep();

// ====================================================================
// FUNCTIONS
// ====================================================================
// LED-Sequence Related
void setAllLeds(uint8_t val)               // COMMON-ANODE → invert
{
  uint8_t lvl = val;
  ledcWrite(PWM_CH_RED , lvl);
  ledcWrite(PWM_CH_GRN , lvl);
  ledcWrite(PWM_CH_BLU , lvl);
  ledcWrite(PWM_CH_YEL , lvl);
}
void setColour(char c, uint8_t val)
{
  uint8_t lvl = val;
  switch (c) {
    case 'R': ledcWrite(PWM_CH_RED , lvl); break;
    case 'G': ledcWrite(PWM_CH_GRN , lvl); break;
    case 'B': ledcWrite(PWM_CH_BLU , lvl); break;
    case 'I': ledcWrite(PWM_CH_YEL , lvl); break;
  }
}
bool parseLedSequence(const uint8_t *buf, uint16_t len)
{
  stepCount = 0;
  repeatCfg = 0;

  char tmp[len + 1];
  memcpy(tmp, buf, len);
  tmp[len] = '\0';

  char *tok = strtok(tmp, ",");
  while (tok && stepCount < MAX_STEPS)
  {
    if (tok[0] == 'C') {                 // repeat counter
      tok = strtok(nullptr, ",");
      repeatCfg = tok ? atoi(tok) : 0;
      break;
    }

    char colour = tok[0];
    tok = strtok(nullptr, ","); if (!tok) break;
    uint8_t lvl = atoi(tok);
    tok = strtok(nullptr, ","); if (!tok) break;
    uint16_t onS = atoi(tok);
    tok = strtok(nullptr, ","); if (!tok) break;
    uint16_t offS = atoi(tok);

    steps[stepCount++] = { colour, lvl, uint32_t(onS)*TICK_MS, uint32_t(offS)*TICK_MS };
    tok = strtok(nullptr, ",");
  }

  return (stepCount > 0);
}
void startSequence()
{
  seqEnabled   = true;
  curStep      = 0;
  inOnTime     = true;
  repeatRemain = repeatCfg ? repeatCfg : 0xFFFFFFFF;  // infinite => large
  setAllLeds(0);
  setColour(steps[0].colour, steps[0].level);
  nextEvent = millis() + steps[0].onMs;
}
void stopSequence()
{
  seqEnabled = false;
  setAllLeds(0);
}

// ====================================================================
// Packet-Related
void saveLatestLedPkt(const uint8_t *data, uint16_t len)
{
  nvs.begin(NS_LED, false);
  nvs.putUInt(KEY_LEN, len);
  nvs.putBytes(KEY_PAY, data, len);
  nvs.end();
}
void sendPollAck()
{
  uint32_t sum = 0;
  auto put = [&](uint8_t b){ Serial.write(b); sum += b; };

  put(0x5A); put(0xA5);
  put(0x00); put(0x00);
  put(DATA_POLL);

  uint16_t cs = sum & 0xFFFF;
  put(uint8_t(cs & 0xFF));
  put(uint8_t(cs >> 8));
}
bool loadLatestLedPkt(uint8_t *data, uint16_t &len)
{
  nvs.begin(NS_LED, true);
  len = nvs.getUInt(KEY_LEN, 0);
  bool ok = (len && len <= PAYLOAD_MAX);
  if (ok) nvs.getBytes(KEY_PAY, data, len);
  nvs.end();
  return ok;
}
void sendStoredLedPkt()
{
  uint16_t len;
  if (!loadLatestLedPkt(payload, len)) len = 0;

  uint32_t sum = 0;
  auto put = [&](uint8_t b){ Serial.write(b); sum += b; };

  put(0x5A); put(0xA5);
  put(len & 0xFF); put(len >> 8);
  put(0x00);

  for (uint16_t i = 0; i < len; ++i) put(payload[i]);

  uint16_t cs = sum & 0xFFFF;
  Serial.write(uint8_t(cs & 0xFF));
  Serial.write(uint8_t(cs >> 8));
}
bool receivePacket()
{
  enum { S1, S2, LEN1, LEN2, TYPE, PAY, CS1, CS2 };
  static uint8_t  st = S1;
  static uint16_t len = 0, idx = 0, sum = 0;
  static uint8_t  csLo = 0, csHi = 0;

  while (Serial.available())
  {
    uint8_t b = Serial.read();
    switch (st)
    {
      case S1:  if (b == 0x5A) { sum = b; st = S2; } break;
      case S2:  if (b == 0xA5) { sum += b; st = LEN1; } else st = S1; break;

      case LEN1: len = b; sum += b; st = LEN2; break;
      case LEN2: len |= uint16_t(b) << 8; sum += b;
                 if (len > PAYLOAD_MAX) { st = S1; break; }
                 st = TYPE; break;

      case TYPE:
        dataType = b; sum += b; idx = 0;
        st = (len == 0) ? CS1 : PAY; break;

      case PAY:
        payload[idx++] = b; sum += b;
        if (idx >= len) st = CS1;
        break;

      case CS1: csLo = b;
                if (b != uint8_t(sum & 0xFF)) { st = S1; break; }
                st = CS2; break;

      case CS2:
        csHi = b;
        if (b != uint8_t(sum >> 8)) { st = S1; break; }

        rxLen  = len;
        pktLen = len + 7;
        pktSum = sum;
        pktChk = uint16_t(csHi) << 8 | csLo;

        if (dataType == DATA_POLL) {     // 0x01
          sendPollAck();
          st = S1;
          return false;
        }

        if (dataType == 0x00)
          saveLatestLedPkt(payload, rxLen);

        if (dataType == 0x02) {
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
static void appendGroup(char *dst, char *&tok)
{
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
void buildPages()
{
  snprintf(pages[0].l1, LCD_COLS + 1, "Hdr:%04X Len:%u", 0x5AA5, rxLen);
  snprintf(pages[0].l2, LCD_COLS + 1, "T:%02X CS:%04X", dataType, pktChk);

  pageCnt = 1;
  if (dataType != 0x00) return;

  memcpy(payStr, payload, rxLen);
  payStr[rxLen] = '\0';

  char *tok = strtok(payStr, ",");
  while (tok && pageCnt < MAX_PAGES)
  {
    pages[pageCnt].l1[0] = pages[pageCnt].l2[0] = '\0';
    appendGroup(pages[pageCnt].l1, tok);
    appendGroup(pages[pageCnt].l2, tok);
    ++pageCnt;
  }

  for (uint8_t i = pageCnt; i < MAX_PAGES; ++i)
    pages[i].l1[0] = pages[i].l2[0] = '\0';
}
void showPage(uint8_t idx)
{
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(pages[idx].l1);
  lcd.setCursor(0, 1); lcd.print(pages[idx].l2);

  Serial.printf("LCD page %u / %u\n", idx, pageCnt - 1);
  Serial.printf("%s\n%s\n", pages[idx].l1, pages[idx].l2);
}

// ====================================================================
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

    unsigned long currentTime = millis();
    unsigned long pressDuration = currentTime - lastPressStart;

    // CASE 2: Long press handling (2000ms-3000ms)
    if (pressDuration >= LONG_PRESS_TIME && pressDuration <= VERY_LONG_PRESS_TIME && !longPressHandled) {
      Serial.println("*Long Press detected...");
      blinkLED();

      Serial.println(just_switched_from_btp_to_usb);

      if (!just_switched_from_btp_to_usb) {
        if (mode == 1) {  // USB mode
          toggleBluetoothConnection();
          Serial.println("USB -> Bluetooth");
        } else {  // Bluetooth mode
          toggleBluetoothConnection();
          Serial.println("Bluetooth -> USB");
        }
      } else {
        delay(1005);
        just_switched_from_btp_to_usb = false;
      }
    }
    // CASE 3: Very long press handling (3 seconds)
    else if (pressDuration > VERY_LONG_PRESS_TIME && !longPressHandled) {
      Serial.println("*Very Long Press detected...");
      blinkLED();
      just_switched_from_btp_to_usb = false;
      longPressHandled = true;  // Mark handled

      // Implement power off logic here
      Serial.println("Powering off...");
      delay(100);  // Debounce
      enterDeepSleep();
    }
  }
  // Button released
  else {
    if (isPressed) {
      isPressed = false;  // Reset pressed state
      unsigned long currentTime = millis();
      unsigned long pressDuration = currentTime - lastPressStart;

      // Simply mark handling true for long press if button is released
      if (pressDuration >= LONG_PRESS_TIME && pressDuration <= VERY_LONG_PRESS_TIME && !longPressHandled) {
        longPressHandled = true;  // Mark handled
      }

      // CASE 1: Short press handling (200ms-2000ms)
      if (pressDuration > SHORT_PRESS_TIME && pressDuration < LONG_PRESS_TIME && !bt_waitingconnect) {
        Serial.println("*Short Press detected...");
        blinkLED();
        mini_flashing = !mini_flashing;
        Serial.println(mini_flashing ? "Mini-flasher ON" : "Mini-flasher OFF");
      }
    }
  }
}
// Function to detect long press on MFB_KEY during startup and BT Pairing mode
bool detectLongPress() {
  unsigned long pressStartTime = millis();

  while (digitalRead(MFB_KEY) == LOW) {  // While button is pressed down
    if (millis() - pressStartTime >= LONG_PRESS_TIME) {
      Serial.println("Long press in detectionLongPress()");
      return true;  // Long press detected
    }
    delay(10);  // Small delay to debounce button
  }

  return false;  // No long press detected
}

// ====================================================================
// Function to initialize Bluetooth connection
void initializeBluetooth() {
  bt_waitingconnect = false;
  // Get the Bluetooth MAC address and set device name
  uint8_t btMac[6];
  //esp_read_mac(btMac, ESP_MAC_BT);
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
  if (mode == 1) {
    if (!bt_waitingconnect) {  // if BT is not connected and waiting for connection, exit with no action.
      initializeBluetooth();
      bt_waitingconnect = true;
      Serial.println("BT is turned ON.");
    }
  } else {  // mode == 0
    mode = 1;
    SerialBT.end();
    bt_waitingconnect = false;
    digitalWrite(LED_BLE, HIGH);  // Turn off Blue LED.
    Serial.println("BT is turned OFF.");
  }
}

// ====================================================================
// Function to blink the LED briefly when the button is released in handleMFB()
void blinkLED() {
  digitalWrite(LED_STA, LOW);
  delay(100);
  digitalWrite(LED_STA, HIGH);
}
void offLED() {
  digitalWrite(LED_USB, HIGH);
  digitalWrite(LED_BLE, HIGH);
  digitalWrite(LED_STA, HIGH);
}
void updateLEDs() {
  digitalWrite(LED_USB, mode == 1 ? LOW : HIGH);  // Green on for USB
  digitalWrite(LED_BLE, mode == 0 ? LOW : HIGH);  // Blue on for BT
}

// ====================================================================
// Sleep handling
void enterDeepSleep() {
  Serial.println("Entering deep sleep...");

  // Clean up before sleep
  powerDownLCD();
  SerialBT.end();
  offLED();
  Serial.flush();
  delay(100);

  // Enter deep sleep
  rtc_gpio_isolate((gpio_num_t)MFB_KEY);
  esp_deep_sleep_start();
}

// Initialization after booting up / waking up
void initialize() {
  // POWERED OFF CASE 1: Keep pressing on for 2 seconds for BT
  if (detectLongPress()) {
    blinkLED();
    Serial.println("Using Bluetooth mode");
    initializeBluetooth();

    while (!SerialBT.hasClient()) {
      if (Count100ms % 10 == 0) {  //every 1000ms.
        digitalWrite(LED_BLE, digitalRead(LED_BLE) ^ 1);
      }

      if (detectLongPress()) {
        Serial.println("Long press detected, switch using USB Mode!");
        break;
      }

      Count100ms++;  // Increment 100ms counter.
      delay(100);
      if (Count100ms == 100) {  //count 10 sec. Prepare for 400ms on/off.
        Count100ms = 0;         //reset the 100ms counter. From 0 to 99.
      }
    }
    offLED();
  }

  if (SerialBT.hasClient()) {
    // Exited loop if Bluetooth is connected
    mode = 0;
    bt_waitingconnect = false;
    updateLEDs();
    Serial.println("Connected via BT! ESP32 is ready to send data.");

    /* Implement Bluetooth Mode logic
      ...
      ...
    */
  } 
  else {
    // POWERED OFF CASE 2: NOT Keep pressing on for 2 seconds for USB Mode
    Serial.println("Using USB Mode! ESP32 is ready to send data.");
    mode = 1;
    bt_waitingconnect = false;
    updateLEDs();

    /* Implement USB Mode logic
      ...
      ...
    */
  }
}

// LCD init and shut down
void initLCD() {
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.begin();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Mini Flasher");
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
  return(esp_adc_cal_raw_to_voltage(ADC_Raw, &adc_chars));
}

/* ----------------------------------------------------------------- */
/* SETUP */
/* ----------------------------------------------------------------- */
void setup() {
  // ESP Sleep
  esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
  esp_sleep_enable_ext0_wakeup((gpio_num_t)MFB_KEY, 0);                   // Config wake-up source
  esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();  // Handle wake scenarios

  // Start Serial monitor for debugging via USB
  Serial.begin(115200);
  delay(100);

  // Pins init
  pinMode(MFB_KEY, INPUT);   // MFB_KEY is active LOW
  pinMode(LOW_BATT, INPUT_PULLUP);  // LOW_BATT is active low.
  pinMode(LED_USB, OUTPUT);
  pinMode(LED_BLE, OUTPUT);
  pinMode(LED_STA, OUTPUT);
  offLED();  // Turn all LEDs off
  initLCD();

  // 1. Wake from sleep
  if (wakeup_reason == ESP_SLEEP_WAKEUP_EXT0) {
    Serial.println("Woke from deep sleep");
    delay(500);
    lcd.print("Waking");
    initialize();
  }

  // 2. Normal boot
  else {
    Serial.println("Woke from Normal boot");
    delay(500);
    lcd.print("Booting");
    initialize();
  }

  mytimer.start();  // Start the timer
}

/* ----------------------------------------------------------------- */
/* LOOP */
/* ----------------------------------------------------------------- */
void loop() {
  //Timer interrupt
  if (mytimer.repeat()) {

    // Battery logger
    int rawValue = analogRead(39);
    float voltage = float(readADC_Cal(rawValue)) / 1000 * 2;
    float voltage_old = (float)rawValue / 4095 * 2 * 3.8;
    lcd.setCursor(8, 1);
    lcd.print(voltage);
    Serial.println(voltage_old);

    // Check MFB state and perform actions accordingly after powering on!!
    handleMFB();

    // Check if Bluetooth is connected
    if (mode == 0) {
      if (!SerialBT.hasClient()) {
        bt_waitingconnect = true;
        mode = 1;
      }
      else {
        /* Implement Bluetooth Mode logic
          ...
          ...
        */
      }
    }
    // What if Bluetooth not connected?
    else {                      // if bt_connected=false only, BLUE LED = off.
      if (bt_waitingconnect) {  // if bt_connected=false and BT wait for connect, toggle BLUE LED.
        digitalWrite(LED_USB, HIGH);
        digitalWrite(LED_STA, HIGH);
        if (Count100ms % 10 == 0) {                         //every 1000ms.
          digitalWrite(LED_BLE, digitalRead(LED_BLE) ^ 1);  // Blink Blue LED when not connected (slow blink)
        }
        if (detectLongPress()) {
          Serial.println("Long press detected, switch using USB Mode!");
          offLED();
          mode = 1;
          bt_waitingconnect = false;
          just_switched_from_btp_to_usb = true;
          updateLEDs();

          /* Implement USB Mode logic
            ...
            ...
          */
        }
      }
    }

    // Check if Bluetooth is reconnected
    if (bt_waitingconnect) {
      if (SerialBT.hasClient()) {
        offLED();
        digitalWrite(LED_BLE, LOW);
        Serial.println("Connected via BT! ESP32 is ready to send data after disconnected.");
        mode = 0;
        bt_waitingconnect = false;
      }
    }

    // Low battery light flashing
    if (voltage <= 3.5) {                         // LOW_BATT is active low.
      digitalWrite(LED_USB, HIGH);
      digitalWrite(LED_BLE, HIGH);
      if (Count100ms % 10 == 0) {                         //every 1000ms.
        digitalWrite(LED_STA, digitalRead(LED_STA) ^ 1);  // Blink RED LED when LOW_BATT = 0.
      }
    } 
    else {
      if (!bt_waitingconnect) {
        digitalWrite(LED_STA, HIGH);
        updateLEDs();
      }
    }

    // Increment 100ms counter.
    Count100ms++;             // Increment 100ms counter.
    if (Count100ms == 100) {  //count 10 sec. Prepare for 400ms on/off.
      Count100ms = 0;         //reset the 100ms counter. From 0 to 99.
    }
  }
}
