from machine import Pin, I2C, ADC, RTC
from neopixel import NeoPixel
import network
import espnow
import time
import math
import struct
import urequests

# HARDWARE
i2c = I2C(0, scl=Pin(18), sda=Pin(19), freq=50000)
MPU_ADDR = 0x68
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')

ldr = ADC(Pin(36))
ldr.atten(ADC.ATTN_11DB)
pot = ADC(Pin(34))
pot.atten(ADC.ATTN_11DB)

np = NeoPixel(Pin(13), 12)
FIRST_LED = 1

# WIFI
SSID = "matt"
PASSWORD = "12345678"

sta = network.WLAN(network.STA_IF)
sta.active(False)
time.sleep(1)
sta.active(True)
sta.connect(SSID, PASSWORD)

timeout = 10
while not sta.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if not sta.isconnected():
    raise Exception("WiFi failed")

print(f"WiFi: {sta.ifconfig()[0]}")

# ESP-NOW
peer_mac = b'\x68\x25\xDD\xE9\xB7\xD8'  # BAG MAC
e = espnow.ESPNow()
e.active(True)
e.add_peer(peer_mac)

# CONFIG
DARK_THRESHOLD = 3000
MOTION_THRESHOLD = 5000
IDLE_TIMEOUT = 180_000
ESPNOW_INTERVAL = 500
API_UPDATE = 600_000

# STATE
mpu_baseline = 0
last_motion = 0
light_on = False
last_espnow = 0
last_api = 0
sunrise_min = 0
sunset_min = 0

# MPU CALIBRATION
print("Calibrating MPU...")
readings = []
for i in range(10):
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    x = (data[0] << 8) | data[1]
    y = (data[2] << 8) | data[3]
    z = (data[4] << 8) | data[5]
    if x > 32767: x -= 65536
    if y > 32767: y -= 65536
    if z > 32767: z -= 65536
    readings.append(math.sqrt(x*x + y*y + z*z))
    time.sleep(0.05)

mpu_baseline = sum(readings) / len(readings)
print(f"MPU baseline: {mpu_baseline:.0f}")

# FUNCTIONS
def detect_motion():
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    x = (data[0] << 8) | data[1]
    y = (data[2] << 8) | data[3]
    z = (data[4] << 8) | data[5]
    if x > 32767: x -= 65536
    if y > 32767: y -= 65536
    if z > 32767: z -= 65536
    current = math.sqrt(x*x + y*y + z*z)
    return abs(current - mpu_baseline) > MOTION_THRESHOLD

def set_light(brightness_pct):
    global light_on
    val = int(brightness_pct * 2.55)
    for i in range(FIRST_LED):
        np[i] = (0, 0, 0)
    for i in range(FIRST_LED, 12):
        np[i] = (val, val, val)  # HVID
    np.write()
    light_on = True

def turn_off_light():
    global light_on
    for i in range(12):
        np[i] = (0, 0, 0)
    np.write()
    light_on = False

def send_espnow(ldr_val, brightness, is_light_on):
    light_byte = 1 if is_light_on else 0
    msg = struct.pack('HBB', ldr_val, brightness, light_byte)
    try:
        e.send(peer_mac, msg)
    except:
        pass

def update_sun_times(lat, lon):
    global sunrise_min, sunset_min
    try:
        response = urequests.get(f"http://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0")
        data = response.json()
        response.close()
        
        sunset_time = data['results']['sunset'].split('T')[1].split('+')[0]
        sunrise_time = data['results']['sunrise'].split('T')[1].split('+')[0]
        
        sunset_h, sunset_m = map(int, sunset_time.split(':')[:2])
        sunrise_h, sunrise_m = map(int, sunrise_time.split(':')[:2])
        
        sunset_h += 1  # CET
        sunrise_h += 1
        
        sunset_min = sunset_h * 60 + sunset_m
        sunrise_min = sunrise_h * 60 + sunrise_m
        
        print(f"API: Sunrise {sunrise_h:02d}:{sunrise_m:02d}, Sunset {sunset_h:02d}:{sunset_m:02d}")
        return True
    except Exception as e:
        print(f"API error: {e}")
        return False

# Initial API (default København - opdateres via ESP-NOW)
update_sun_times(55.6761, 12.5683)

# MAIN LOOP
print("Front ESP32 running...\n")
last_debug = 0

while True:
    now = time.ticks_ms()
    
    # SENSORS
    ldr_value = ldr.read()
    pot_value = pot.read()
    brightness = int((pot_value / 4095) * 100)
    
    is_dark_ldr = ldr_value < DARK_THRESHOLD
    
    rtc = RTC()
    now_time = rtc.datetime()
    current_min = now_time[4] * 60 + now_time[5]
    is_dark_time = current_min < sunrise_min or current_min > sunset_min
    
    is_dark = is_dark_ldr or is_dark_time
    
    motion_detected = detect_motion()
    if motion_detected:
        last_motion = now
    
    idle_time = time.ticks_diff(now, last_motion)
    should_light = is_dark and (idle_time < IDLE_TIMEOUT)
    
    # LIGHT CONTROL
    if should_light and not light_on:
        send_espnow(ldr_value, brightness, True)
        time.sleep_ms(50)
        set_light(brightness)
        print(f"⚪ FRONT ON ({brightness}%)")
        
    elif not should_light and light_on:
        send_espnow(ldr_value, brightness, False)
        time.sleep_ms(50)
        turn_off_light()
        print(f"⚫ FRONT OFF")
        
    elif should_light and light_on:
        set_light(brightness)
    
    # ESP-NOW PERIODIC
    if time.ticks_diff(now, last_espnow) > ESPNOW_INTERVAL:
        send_espnow(ldr_value, brightness, light_on)
        last_espnow = now
    
    # DEBUG
    if time.ticks_diff(now, last_debug) > 2000:
        print(f"⚪{light_on} | LDR:{ldr_value} | Bright:{brightness}% | {now_time[4]:02d}:{now_time[5]:02d}")
        last_debug = now
    
    time.sleep(0.1)