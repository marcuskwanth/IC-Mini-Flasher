/*************************************************************************
 *  Mini-Flasher – LCD monitor  
 *  ASCII-payload, 2-groups-per-page, remembers last LED packet in NVS  
 *  Added: “123456…” marquee that is shown for ≈0.7 s whenever a
 *         POLL-LINK packet (type 0x01) is received.
 *
 *  Packet format
 *      5A A5 <lenLE> <type> <ASCII payload> <CSum16 LE>
 *
 *      type 0x00 : LED-setting  (stored, paged on LCD)
 *           0x01 : Poll-link    (board answers 7-byte ACK + marquee)
 *           0x02 : Load-setting (board returns the stored 0x00 packet)
 *
 *  Hardware
 *      • ESP32 DevKit (UART0 115200 Bd)
 *      • 16×2 LCD with I²C backpack (address 0x27, SDA21 / SCL22)
 *************************************************************************/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Preferences.h>
#include <string.h>

/* ─────────── user-adjustable constants ──────────────────────────── */
#define I2C_SDA         21
#define I2C_SCL         22
#define LCD_ADDR      0x27
#define PAGE_TIME_MS 7000                     // auto-turn page every 7 s

constexpr uint8_t  LCD_COLS     = 16;
constexpr uint8_t  LCD_ROWS     =  2;
constexpr uint16_t PAYLOAD_MAX  = 1002;
constexpr uint16_t PKT_MAX      = PAYLOAD_MAX + 7;
constexpr uint8_t  MAX_PAGES    = 60;

/* POLL-LINK marquee parameters (must be < watchdog period on PC side) */
constexpr uint8_t  DATA_POLL    = 0x01;
constexpr uint16_t MARQUEE_DLY  = 250;        // ms between scroll steps
constexpr uint16_t MARQUEE_TIME = 700;        // total marquee duration

/* ─────────── NVS namespace / keys ───────────────────────────────── */
Preferences nvs;
const char *NS_LED  = "led_pkt";
const char *KEY_LEN = "len";
const char *KEY_PAY = "pay";

/* ─────────── global objects / buffers ───────────────────────────── */
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

uint8_t  payload[PAYLOAD_MAX];                // raw payload bytes
uint16_t rxLen  = 0;                          // length just received
uint16_t pktChk = 0;                          // checksum of last packet
uint8_t  dataType = 0;                        // type of last packet

struct Page { char l1[LCD_COLS + 1]; char l2[LCD_COLS + 1]; };
Page     pages[MAX_PAGES];
uint8_t  pageCnt   = 1;                       // number of LCD pages
uint8_t  pageIndex = 0;                       // page currently shown
uint32_t nextTurn  = 0;                       // time for next page turn

/* ─────────── forward declarations ───────────────────────────────── */
void saveLatestLedPkt(const uint8_t*, uint16_t);
bool loadLatestLedPkt(uint8_t*, uint16_t&);
void sendStoredLedPkt();
void sendPollAck();
void runPollMarquee();
bool receivePacket();
void buildPages();
void showPage(uint8_t);

/* ================================================================= */
void setup()
{
  Serial.begin(115200);
  while (!Serial) {}                          // wait for USB-CDC ready

  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  lcd.begin();
  lcd.backlight();
  lcd.print("Waiting packet");

  Serial.println("\nMini-Flasher LCD monitor ready.");
}

/* ================================================================= */
void loop()
{
  /* check serial, process complete packet if available */
  if (receivePacket()) {
    buildPages();
    pageIndex = 0;
    showPage(pageIndex);
    nextTurn = millis() + PAGE_TIME_MS;
  }

  /* automatic page turning */
  if (pageCnt && (int32_t)(millis() - nextTurn) >= 0) {
    pageIndex = (pageIndex + 1) % pageCnt;
    showPage(pageIndex);
    nextTurn += PAGE_TIME_MS;
  }
}

/* ───────────────── helpers for NVS, ACK and marquee ─────────────── */
void saveLatestLedPkt(const uint8_t *data, uint16_t len)
{
  nvs.begin(NS_LED, false);          // read-write
  nvs.putUInt(KEY_LEN, len);
  nvs.putBytes(KEY_PAY, data, len);
  nvs.end();
}

bool loadLatestLedPkt(uint8_t *data, uint16_t &len)
{
  nvs.begin(NS_LED, true);           // read-only
  len = nvs.getUInt(KEY_LEN, 0);
  bool ok = (len && len <= PAYLOAD_MAX);
  if (ok) nvs.getBytes(KEY_PAY, data, len);
  nvs.end();
  return ok;
}

/* return stored LED packet (type 0x00) to PC */
void sendStoredLedPkt()
{
  uint16_t len;
  if (!loadLatestLedPkt(payload, len)) len = 0;

  uint32_t sum = 0;
  auto put = [&](uint8_t b){ Serial.write(b); sum += b; };

  put(0x5A); put(0xA5);
  put(len & 0xFF); put(len >> 8);
  put(0x00);                              // type 0x00

  for (uint16_t i = 0; i < len; ++i) put(payload[i]);

  uint16_t cs = sum & 0xFFFF;
  put(uint8_t(cs & 0xFF));
  put(uint8_t(cs >> 8));
}

/* 7-byte ACK for poll-link */
void sendPollAck()
{
  uint8_t pkt[7] = {0x5A, 0xA5, 0x00, 0x00, DATA_POLL, 0x00, 0x00};
  uint16_t sum   = 0x5A + 0xA5 + DATA_POLL;  // only header+type
  pkt[5] = uint8_t(sum & 0xFF);
  pkt[6] = uint8_t(sum >> 8);
  Serial.write(pkt, 7);
}

/* show “123456…” for ≤ MARQUEE_TIME or until next byte arrives */
void runPollMarquee()
{
  static const char pat[] = "123456123456123456";   // 18 chars
  uint8_t  offset = 0;
  uint32_t t0     = millis();

  while ((millis() - t0) < MARQUEE_TIME && !Serial.available())
  {
    lcd.clear();
    lcd.setCursor(0, 0); lcd.print(&pat[offset]);           // first row
    lcd.setCursor(0, 1); lcd.print(&pat[(offset + 6) % 18]); // second
    offset = (offset + 1) % 6;
    delay(MARQUEE_DLY);
  }
}

/* ───────────────── LCD page formatting ──────────────────────────── */
static void appendGroup(char *dst, char *&tok)
{
  if (!tok) return;

  if (tok[0] == 'C') {                      // cycles marker
    char *cnt = (tok = strtok(nullptr, ","));           // after 'C'
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

void buildPages()
{
  snprintf(pages[0].l1, LCD_COLS + 1, "Hdr:%04X Len:%u", 0x5AA5, rxLen);
  snprintf(pages[0].l2, LCD_COLS + 1, "T:%02X CS:%04X", dataType, pktChk);

  pageCnt = 1;

  if (dataType != 0x00) return;            // only LED packets get pages

  static char payStr[PAYLOAD_MAX + 1];
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

  Serial.printf("\nLCD page %u / %u\n%s\n%s\n",
                idx, pageCnt - 1, pages[idx].l1, pages[idx].l2);
}

/* ───────────────── serial packet receiver ───────────────────────── */
bool receivePacket()
{
  enum { S1, S2, LEN1, LEN2, TYPE, PAY, CS1, CS2 };
  static uint8_t  st   = S1;
  static uint16_t len  = 0, idx = 0, sum = 0;
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
                 if (len > PAYLOAD_MAX)   { st = S1; break; }
                 st = TYPE; break;

      case TYPE:
        dataType = b; sum += b; idx = 0;
        st = (len == 0) ? CS1 : PAY;
        break;

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

        /* packet OK */
        rxLen  = len;
        pktChk = uint16_t(csHi) << 8 | csLo;

        /* POLL-LINK -------------------------------------------------- */
        if (dataType == DATA_POLL) {
          sendPollAck();
          runPollMarquee();           // show pattern briefly
          st = S1;
          return false;               // no pages to build
        }

        /* LED-setting store ------------------------------------------ */
        if (dataType == 0x00)
          saveLatestLedPkt(payload, rxLen);

        /* host requests stored packet ------------------------------- */
        if (dataType == 0x02)
          sendStoredLedPkt();

        st = S1;
        return true;                  // let caller build / show pages
    }
  }
  return false;
}