/*************************************************************************
 *  Mini-Flasher – LCD monitor (ASCII-payload version, 2-groups-per-page)
 *                 now with NVS “remember last LED packet”
 *
 *  Packet:
 *    5A A5 <lenLE> <type> <ASCII payload> <CSum16 LE>
 *
 *  Type:
 *      0x00  LED setting        (stored in flash, paged on LCD)
 *      0x01  Poll link          (status page only)
 *      0x02  Load setting       (board answers with the stored 0x00 packet)
 *
 *  Hardware:
 *      • ESP32 DevKit (UART0 115200 Bd)
 *      • 16×2 LCD + I²C backpack (address 0x27)
 *************************************************************************/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Preferences.h>
#include <string.h>

/* ======================== user constants ========================== */
#define I2C_SDA      21
#define I2C_SCL      22
#define LCD_ADDR   0x27
#define PAGE_TIME_MS 7000

constexpr uint8_t  LCD_COLS     = 16;
constexpr uint8_t  LCD_ROWS     =  2;
constexpr uint16_t PAYLOAD_MAX  = 1002;
constexpr uint16_t PKT_MAX      = PAYLOAD_MAX + 7;   // hdr+len+type+cs
constexpr uint8_t  MAX_PAGES    = 60;

/* ===================== NVS namespace / keys ======================= */
Preferences nvs;
const char *NS_LED  = "led_pkt";    // ≤15 chars
const char *KEY_LEN = "len";
const char *KEY_PAY = "pay";

/* ===================== global objects / buffers =================== */
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

uint8_t  payload[PAYLOAD_MAX];
uint8_t  packet [PKT_MAX];
uint16_t rxLen  = 0;
uint16_t pktLen = 0;
uint16_t pktSum = 0;
uint16_t pktChk = 0;
uint8_t  dataType = 0;
uint8_t DATA_POLL = 0x01;

char     payStr[PAYLOAD_MAX + 1];

struct Page { char l1[LCD_COLS + 1]; char l2[LCD_COLS + 1]; };
Page pages[MAX_PAGES];
uint8_t  pageCnt   = 1;
uint8_t  pageIndex = 0;
uint32_t nextTurn  = 0;

/* ===================== forward declarations ======================= */
void saveLatestLedPkt(const uint8_t *data, uint16_t len);
bool loadLatestLedPkt(uint8_t *data, uint16_t &len);
void sendStoredLedPkt();

/* ================================================================= */
void setup()
{
  Serial.begin(115200);
  while (!Serial) {}

  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  lcd.begin();
  lcd.backlight();
  lcd.print("Waiting packet");

  Serial.println("\nASCII-payload LCD monitor ready.");
}

/* ================================================================= */
void loop()
{
  if (receivePacket()) {
    buildPages();
    pageIndex = 0;
    showPage(pageIndex);
    nextTurn = millis() + PAGE_TIME_MS;
  }

  if (pktLen && (int32_t)(millis() - nextTurn) >= 0) {
    pageIndex = (pageIndex + 1) % pageCnt;
    showPage(pageIndex);
    nextTurn += PAGE_TIME_MS;
  }
}

/* ----------------------------------------------------------------- */
/*  STORE LATEST LED PACKET IN FLASH                                 */
/* ----------------------------------------------------------------- */
void saveLatestLedPkt(const uint8_t *data, uint16_t len)
{
  nvs.begin(NS_LED, false);           // RW
  nvs.putUInt(KEY_LEN, len);
  nvs.putBytes(KEY_PAY, data, len);
  nvs.end();
}
void sendPollAck()
{
  uint32_t sum = 0;
  auto put = [&](uint8_t b){ Serial.write(b); sum += b; };

  put(0x5A);            // sync
  put(0xA5);
  put(0x00); put(0x00); // LEN = 0
  put(DATA_POLL);       // TYPE = 0x01

  uint16_t cs = sum & 0xFFFF;
  put(uint8_t(cs & 0xFF));   // CS low
  put(uint8_t(cs >> 8));     // CS high
}

/* ----------------------------------------------------------------- */
/*  LOAD LATEST LED PACKET FROM FLASH                                */
/*  returns false if nothing stored                                  */
/* ----------------------------------------------------------------- */
bool loadLatestLedPkt(uint8_t *data, uint16_t &len)
{
  nvs.begin(NS_LED, true);            // read-only
  len = nvs.getUInt(KEY_LEN, 0);
  bool ok = (len && len <= PAYLOAD_MAX);
  if (ok) nvs.getBytes(KEY_PAY, data, len);
  nvs.end();
  return ok;
}

/* ----------------------------------------------------------------- */
/*  TRANSMIT STORED PACKET BACK TO PC                                */
/* ----------------------------------------------------------------- */
void sendStoredLedPkt()
{
    uint16_t len;
    if (!loadLatestLedPkt(payload, len)) len = 0;

    uint32_t sum = 0;                         // accumulate in wider type
    auto put = [&](uint8_t b){ Serial.write(b); sum += b; };

    put(0x5A); put(0xA5);
    put(len & 0xFF); put(len >> 8);
    put(0x00);

    for (uint16_t i = 0; i < len; ++i) put(payload[i]);

    /* -------- send checksum without touching it again -------- */
    uint16_t csum = sum & 0xFFFF;
    Serial.write(uint8_t(csum & 0xFF));       // low
    Serial.write(uint8_t(csum >> 8));         // high
}

/* ================== helper: append next CSV group ================= */
static void appendGroup(char *dst, char *&tok)
{
  if (!tok) return;

  if (tok[0] == 'C') {                // final group
    char *cnt = (tok = strtok(nullptr, ","));   // token after 'C'
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

  if (dataType != 0x00) return;       // only LED pages afterwards

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
        dataType = b;
        sum += b;
        idx = 0;
        st  = (len == 0) ? CS1 : PAY;   // skip PAY when there is no payload
        break;

      case PAY:
        if (len == 0) {                 // nothing to read
            st = CS1;
            break;
        }
        payload[idx++] = b;
        sum += b;
        if (idx >= len) st = CS1;
        break;

      case CS1:  csLo = b;
                 if (b != uint8_t(sum & 0xFF)) { st = S1; break; }
                 st = CS2; break;

      case CS2:                                 // << whole new body >>
              csHi = b;
              if (b != uint8_t(sum >> 8)) { st = S1; break; }

              rxLen  = len;
              pktLen = len + 7;
              pktSum = sum;
              pktChk = uint16_t(csHi) << 8 | csLo;

              /* -----------  NEW BRANCH: POLL-LINK answer  --------------- */
              if (dataType == DATA_POLL) {            // 0x01
                  sendPollAck();                      // 7-byte ACK
                  st = S1;
                  return false;                       // nothing else to do
              }
              /* -----------  existing branches stay unchanged ------------ */
              if (dataType == 0x00)                   // save LED settings
                  saveLatestLedPkt(payload, rxLen);

              if (dataType == 0x02) {                 // request-data
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