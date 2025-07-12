/*************************************************************************
 *  Mini-Flasher — LCD monitor + PWM colour sequencer
 *
 *  Added features
 *    • Parses 0x00 “LED setting” CSV payload and plays a sequence on
 *      four PWM channels  (R | G | B | I->yellow)
 *    • Push-button (GPIO 4, active-LOW) toggles the sequencer
 *        – OFF  → all outputs low
 *        – ON   → sequence restarts at step 0
 *    • Sequence definition is kept in NVS; parsed once at boot
 *
 *  Packet format (unchanged)
 *    5A A5  <lenLE>  <type>  <payload …>  <checksum16 LE>
 *************************************************************************/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Preferences.h>
#include <string.h>
#include <stdlib.h>

/* ======================== user constants ========================== */
#define I2C_SDA      21
#define I2C_SCL      22
#define LCD_ADDR   0x27
#define PAGE_TIME_MS 7000

/* ------------ GPIO + LED-PWM stuff ------------------------------ */
#define RED_PIN   14
#define GRN_PIN   25
#define BLUE_PIN  12
#define YEL_PIN   26          // ‘I’ in the CSV
#define MFB_KEY    4          // push-button, active-LOW

constexpr uint8_t  PWM_CH_RED  = 0;
constexpr uint8_t  PWM_CH_GRN  = 1;
constexpr uint8_t  PWM_CH_BLU  = 2;
constexpr uint8_t  PWM_CH_YEL  = 3;
constexpr uint32_t PWM_FREQ    = 5000;
constexpr uint8_t  PWM_BITS    = 8;            // intensity 0-255

/* ======================== LCD / packet limits ==================== */
constexpr uint8_t  LCD_COLS     = 16;
constexpr uint8_t  LCD_ROWS     =  2;
constexpr uint16_t PAYLOAD_MAX  = 1002;
constexpr uint16_t PKT_MAX      = PAYLOAD_MAX + 7;
constexpr uint8_t  MAX_PAGES    = 60;

/* ===================== NVS namespace / keys ====================== */
Preferences nvs;
const char *NS_LED  = "led_pkt";
const char *KEY_LEN = "len";
const char *KEY_PAY = "pay";

/* ===================== global objects / buffers ================== */
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

uint8_t  payload[PAYLOAD_MAX];
uint16_t rxLen  = 0;
uint16_t pktLen = 0;
uint16_t pktSum = 0;
uint16_t pktChk = 0;
uint8_t  dataType = 0;
uint8_t  DATA_POLL = 0x01;

char     payStr[PAYLOAD_MAX + 1];

struct Page { char l1[LCD_COLS + 1]; char l2[LCD_COLS + 1]; };
Page pages[MAX_PAGES];
uint8_t  pageCnt   = 1;
uint8_t  pageIndex = 0;
uint32_t nextTurn  = 0;
uint32_t TICK_MS = 100;  

/* ============== colour-sequence description ====================== */
struct LedStep {
  char     colour;   // 'R','G','B','I'
  uint8_t  level;    // 0-255
  uint32_t onMs;     // milliseconds
  uint32_t offMs;
};
constexpr uint16_t MAX_STEPS = 250;
LedStep  steps[MAX_STEPS];
uint16_t stepCount     = 0;
uint32_t repeatCfg     = 0;    // 0 = infinite
uint32_t repeatRemain  = 0;

/* ============== sequencer runtime state ========================== */
bool     seqEnabled = false;
uint16_t curStep    = 0;
bool     inOnTime   = true;
uint32_t nextEvent  = 0;

/* ===================== forward declarations ====================== */
bool  receivePacket();
void  buildPages();
void  showPage(uint8_t idx);
void  saveLatestLedPkt(const uint8_t *data, uint16_t len);
bool  loadLatestLedPkt(uint8_t *data, uint16_t &len);
void  sendStoredLedPkt();
void  sendPollAck();

/* ---- new helpers ------------------------------------------------ */
void setAllLeds(uint8_t val);
void setColour(char c, uint8_t val);
bool parseLedSequence(const uint8_t *buf, uint16_t len);
void startSequence();
void stopSequence();

/* ================================================================= */
void setup()
{
  Serial.begin(115200);
  while (!Serial) {}

  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  lcd.begin();
  lcd.backlight();
  lcd.print("Waiting packet");

  /* -------- GPIO / PWM / button --------------------------------- */
  pinMode(MFB_KEY, INPUT_PULLUP);

  ledcSetup(PWM_CH_RED , PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_GRN , PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_BLU , PWM_FREQ, PWM_BITS);
  ledcSetup(PWM_CH_YEL , PWM_FREQ, PWM_BITS);

  ledcAttachPin(RED_PIN , PWM_CH_RED);
  ledcAttachPin(GRN_PIN , PWM_CH_GRN);
  ledcAttachPin(BLUE_PIN, PWM_CH_BLU);
  ledcAttachPin(YEL_PIN , PWM_CH_YEL);

  setAllLeds(0);

  /* -------- parse stored packet at boot -------------------------- */
  uint16_t lenBoot;
  if (loadLatestLedPkt(payload, lenBoot))
    parseLedSequence(payload, lenBoot);

  Serial.println("\nASCII-payload LCD monitor ready.");
}

/* ================================================================= */
void loop()
{
  /* 1. UART packet handling */
  if (receivePacket()) {
    buildPages();
    pageIndex = 0;
    showPage(pageIndex);
    nextTurn = millis() + PAGE_TIME_MS;

    if (dataType == 0x00)                 // new LED sequence arrived
      parseLedSequence(payload, rxLen);
  }

  /* 2. LCD page rotation */
  if (pktLen && (int32_t)(millis() - nextTurn) >= 0) {
    pageIndex = (pageIndex + 1) % pageCnt;
    showPage(pageIndex);
    nextTurn += PAGE_TIME_MS;
  }

  /* 3. push-button (edge detection, active-LOW) */
  static bool lastBtn = HIGH;
  bool now = digitalRead(MFB_KEY);
  if (lastBtn == HIGH && now == LOW) {
    if (seqEnabled)
      stopSequence();
    else if (stepCount)
      startSequence();
  }
  lastBtn = now;

  /* 4. non-blocking sequencer state machine */
  if (seqEnabled && (int32_t)(millis() - nextEvent) >= 0)
  {
    if (inOnTime) {
      setAllLeds(0);                       // enter OFF phase
      inOnTime = false;
      nextEvent += steps[curStep].offMs;
    } else {
      /* move to next step */
      inOnTime = true;
      curStep++;
      if (curStep >= stepCount) {
        /* list finished */
        if (repeatCfg == 0) {              // infinite
          curStep = 0;
        } else {
          if (repeatRemain > 1) {
            repeatRemain--;
            curStep = 0;
          } else {                         // done
            stopSequence();
            return;
          }
        }
      }
      setColour(steps[curStep].colour, steps[curStep].level);
      nextEvent = millis() + steps[curStep].onMs;
    }
  }
}

/* ----------------------------------------------------------------- */
/*                    ---  NEW helper code  ---                      */
/* ----------------------------------------------------------------- */
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

/* ----------------------------------------------------------------- */
/*                 --- original helper functions ---                 */
/* ----------------------------------------------------------------- */
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

/* ================== helper: append next CSV group ================= */
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

/* ================== format all pages ============================== */
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

/* ================== show one page on LCD ========================== */
void showPage(uint8_t idx)
{
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(pages[idx].l1);
  lcd.setCursor(0, 1); lcd.print(pages[idx].l2);

  Serial.printf("LCD page %u / %u\n", idx, pageCnt - 1);
  Serial.printf("%s\n%s\n", pages[idx].l1, pages[idx].l2);
}

/* ================== packet receiver =============================== */
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