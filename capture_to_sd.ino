#include "esp_camera.h"
#include "FS.h"
#include "SD_MMC.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ===== AI Thinker ESP32-CAM Pins =====
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===== Settings =====
#define BOOT_BUTTON_PIN    0
#define LED_PIN            33
#define CAPTURE_COUNT      1
#define CAPTURE_DELAY_MS   500
#define FOLDER_NAME        "/photos"

int imageCount = 1;

// ===== Camera Init =====
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  Serial.printf("Sensor PID  : 0x%02X\n", s->id.PID);
  Serial.printf("Sensor MID  : 0x%04X\n", (s->id.MIDH << 8) | s->id.MIDL);
  Serial.printf("Frame Size  : %d\n", s->status.framesize);
  Serial.printf("JPEG Quality: %d\n", s->status.quality);


  Serial.println("Camera ready");
  return true;
}

// ===== SD Init =====
bool initSD() {
  if (!SD_MMC.begin()) {
    Serial.println("SD init failed");
    return false;
  }

  if (SD_MMC.cardType() == CARD_NONE) {
    Serial.println("No SD card");
    return false;
  }

  if (!SD_MMC.exists(FOLDER_NAME)) {
    SD_MMC.mkdir(FOLDER_NAME);
  }

  while (true) {
    char path[40];
    sprintf(path, "%s/img_%03d.jpg", FOLDER_NAME, imageCount);
    if (!SD_MMC.exists(path)) break;
    imageCount++;
  }

  Serial.printf("Start from img_%03d.jpg\n", imageCount);
  return true;
}

// ===== Capture =====
bool captureAndSave() {
  digitalWrite(LED_PIN, LOW);

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Capture failed");
    digitalWrite(LED_PIN, HIGH);
    return false;
  }

  char filepath[40];
  sprintf(filepath, "%s/img_%03d.jpg", FOLDER_NAME, imageCount);

  File file = SD_MMC.open(filepath, FILE_WRITE);
  if (!file) {
    Serial.println("File open failed");
    esp_camera_fb_return(fb);
    digitalWrite(LED_PIN, HIGH);
    return false;
  }

  file.write(fb->buf, fb->len);
  file.close();
  esp_camera_fb_return(fb);

  Serial.printf("Saved: %s\n", filepath);
  imageCount++;

  digitalWrite(LED_PIN, HIGH);
  return true;
}

void blinkLED(int times, int delayMs = 100) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, LOW);
    delay(delayMs);
    digitalWrite(LED_PIN, HIGH);
    delay(delayMs);
  }
}

// ===== Setup =====
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);
  delay(500);

  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);

  bool camOK = initCamera();
  bool sdOK  = initSD();

  if (camOK && sdOK) {
    Serial.println("System ready");
    blinkLED(3, 150);
  } else {
    Serial.println("System error");
    blinkLED(10, 50);
    while (true) delay(1000);
  }
}

// ===== Loop =====
bool lastButtonState = HIGH;

void loop() {
  bool currentButton = digitalRead(BOOT_BUTTON_PIN);

  if (lastButtonState == HIGH && currentButton == LOW) {
    delay(50);

    if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
      Serial.printf("Capturing %d image(s)\n", CAPTURE_COUNT);

      int successCount = 0;

      for (int i = 0; i < CAPTURE_COUNT; i++) {
        if (captureAndSave()) {
          successCount++;
        }

        if (i < CAPTURE_COUNT - 1) {
          delay(CAPTURE_DELAY_MS);
        }
      }

      Serial.printf("Done: %d/%d\n", successCount, CAPTURE_COUNT);

      blinkLED(successCount, 200);

      while (digitalRead(BOOT_BUTTON_PIN) == LOW) delay(10);
    }
  }

  lastButtonState = currentButton;
  delay(10);
}
