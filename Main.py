import time
import network
import dht
import gc
from machine import Pin, I2C, ADC

from mpu6050_handler import MPU6050Handler
from neopixel_handler import NeoPixelHandler
from power_monitor import PowerMonitor
from lcd_handler import LCDHandler
from espnow_receiver import ESPNowReceiver
from tb_client import ThingsBoardClient
from buzzer_music import music

# ===================== KONFIG =====================
WIFI_SSID = "matt"
WIFI_PASS = "12345678"

TB_SERVER = "demo.thingsboard.io"
TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"

IDLE_TIME = 1_000
TELEMETRY_INTERVAL = 10_000

# ===================== BOOT =====================
print("\n" + "=" * 50)
print("SMART BICYCLE BOOT")
print("=" * 50)

# ===================== I2C BUSSER =====================
# PCB / power / LCD
i2c_main = I2C(0, scl=Pin(18), sda=Pin(19), freq=50_000)
time.sleep(0.5)

print("\n1. Initializing hardware modules...")

print("Main I2C devices:", [hex(d) for d in i2c_main.scan()])

# ===================== HARDWARE =====================
mpu = MPU6050Handler(i2c=i2c_main, motion_threshold=5000)
neopixel = NeoPixelHandler(pin=13, num_leds=12, first_led=0)
power = PowerMonitor(i2c_main, battery_pin=35, battery_capacity=2000)
lcd = LCDHandler()

dht_sensor = dht.DHT11(Pin(14))

# Alarm
alarm_led = Pin(26, Pin.OUT)
alarm_led.value(0)

alarm_melody = "0 G5 2 0;2 E5 2 0;4 G5 2 0;6 E5 2 0"
alarm_sound = music(
    songString=alarm_melody,
    looping=True,
    tempo=2,
    duty=50000,
    pin=Pin(15)
)
alarm_sound.stop()

# LDR / Pot
ldr = ADC(Pin(36))
ldr.atten(ADC.ATTN_11DB)

pot = ADC(Pin(34))
pot.atten(ADC.ATTN_11DB)

# ===================== SYSTEM STATE =====================
system_enabled = True
auto_armed = False
alarm_active = False
light_on = False

last_motion = time.ticks_ms()
last_telemetry = 0

lcd_screen = 0
last_lcd_rotation = 0
last_lcd_update = 0

LCD_UPDATE_INTERVAL = 1000

# ===================== MPU CALIBRATION =====================
print("\n2. Calibrating MPU...")
mpu.calibrate(samples=10, lcd=lcd.lcd if lcd.available else None)

# ===================== WIFI =====================
print("\n3. Connecting WiFi...")
lcd.clear()
lcd.write("Connecting WiFi...", 0)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)

timeout = 10
while not wlan.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if not wlan.isconnected():
    raise Exception("WiFi failed")

ip = wlan.ifconfig()[0]
print("✓ WiFi:", ip)

# ===================== THINGSBOARD =====================
def on_rpc(req_id, method, params):
    global system_enabled, auto_armed, alarm_active, last_motion

    reply = "false"

    if method == "getState":
        reply = str(system_enabled).lower()

    elif method == "setState":
        system_enabled = bool(params)
        if not system_enabled:
            alarm_active = False
            auto_armed = False
            alarm_led.value(0)
            alarm_sound.stop()
            neopixel.set_green()
        else:
            last_motion = time.ticks_ms()

        reply = str(system_enabled).lower()

    tb.client.send_rpc_reply(req_id, reply)

tb = ThingsBoardClient(TB_SERVER, TB_TOKEN, rpc_handler=on_rpc)

# ===================== ESPNOW =====================
espnow = ESPNowReceiver(rear_mac=b'\x68\x25\xDD\xE9\xB7\xD8')

print("\n" + "=" * 50)
print("SYSTEM READY")
print("=" * 50)

lcd.clear()
lcd.show_status_screen(
    system_enabled,
    auto_armed,
    light_on,
    power.get_power_stats()["battery_pct"],
    None
)

neopixel.set_green()

# ===================== MAIN LOOP =====================
while True:
    now = time.ticks_ms()

    tb.check_messages()
    espnow.receive()

    gps_lat, gps_lon = espnow.get_gps()
    rear_battery = espnow.get_battery()

    # ---------- MOTION ----------
    if system_enabled and mpu.available:
        if mpu.detect_motion():
            last_motion = now

        if not auto_armed and time.ticks_diff(now, last_motion) > IDLE_TIME:
            auto_armed = True
            neopixel.clear()

        if auto_armed and not alarm_active:
            alarm_active = True
            alarm_led.value(1)
            alarm_sound.resume()
            neopixel.set_red()

    # ---------- TELEMETRY ----------
    if time.ticks_diff(now, last_telemetry) > TELEMETRY_INTERVAL:
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
        except:
            temp = None
            hum = None

        stats = power.get_power_stats()

        tb.send_telemetry({
            "temp": temp,
            "humidity": hum,
            "battery": stats["battery_pct"],
            "current": stats["current_ma"],
            "runtime": stats["runtime_hours"],
            "alarm": alarm_active,
            "armed": auto_armed,
            "lat": gps_lat,
            "lon": gps_lon,
            "rear_battery": rear_battery,
            "free_mem": gc.mem_free()
        })

        last_telemetry = now

    time.sleep(0.05)
