import time
import network
import dht
import gc
from machine import Pin, I2C, ADC, PWM

from mpu6050_handler import MPU6050Handler
from neopixel_handler import NeoPixelHandler
from power_monitor import PowerMonitor
from lcd_handler import LCDHandler
from espnow_receiver import ESPNowReceiver
from tb_client import ThingsBoardClient

# ===================== KONFIG =====================
WIFI_SSID = "matt"
WIFI_PASS = "12345678"

TB_SERVER = "demo.thingsboard.io"  # eller "thingsboard.cloud"
TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"

IDLE_TIME = 30_000  # 30 sek til auto-arm
TELEMETRY_INTERVAL = 10_000  # Send hver 10. sek
ALARM_TELEMETRY_INTERVAL = 10_000

# ===================== BOOT =====================
print("\n" + "=" * 50)
print("SMART BICYCLE BOOT")
print("=" * 50)

# ===================== I2C BUSSER =====================
i2c_main = I2C(0, scl=Pin(18), sda=Pin(19), freq=50_000)
time.sleep(0.5)

print("Main I2C devices:", [hex(d) for d in i2c_main.scan()])

# ===================== HARDWARE =====================
mpu = MPU6050Handler(i2c=i2c_main, motion_threshold=20000)
neopixel = NeoPixelHandler(pin=13, num_leds=12, first_led=0)
power = PowerMonitor(i2c_main, battery_pin=35, battery_capacity=2000)
lcd = LCDHandler()

dht_sensor = dht.DHT11(Pin(14))

# Alarm
alarm_led = Pin(26, Pin.OUT)
alarm_led.value(0)

buzzer_pin = Pin(15, Pin.OUT)
buzzer_pwm = None

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
last_motion_trigger = 0

LCD_UPDATE_INTERVAL = 1000
MOTION_DEBOUNCE = 500

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



# ===================== RPC HANDLER =====================
def on_rpc(req_id, method, params):
    global system_enabled, auto_armed, alarm_active, last_motion, buzzer_pwm
    
    if method == "setState":
        system_enabled = bool(params)
        if not system_enabled:
            alarm_active = False
            auto_armed = False
            alarm_led.value(0)
            if buzzer_pwm:
                buzzer_pwm.deinit()
                buzzer_pwm = None
            neopixel.set_green()
        else:
            last_motion = time.ticks_ms()
    
    if tb.client is not None:
        tb.client.send_rpc_reply(req_id, {"success": True, "state": system_enabled})

# ===================== THINGSBOARD =====================
print("\n4. Connecting ThingsBoard...")

tb = ThingsBoardClient(TB_SERVER, TB_TOKEN, rpc_handler=on_rpc)
tb.reconnect_delay = 60000

print("⚠️ TB will connect in background")

# ===================== ESPNOW =====================
espnow = ESPNowReceiver(rear_mac=b'\x68\x25\xDD\xE9\xB7\xD8')

print("\n" + "=" * 50)
print("SYSTEM READY")
print("=" * 50)

print("Testing buzzer...")
buzzer_test = PWM(Pin(15), freq=2000, duty=512)
time.sleep(1)
buzzer_test.deinit()
print("Buzzer test complete")

lcd.clear()
lcd.show_status_screen(
    system_enabled,
    auto_armed,
    light_on,
    power.get_power_stats()["battery_pct"],
    None
)

neopixel.set_green()

print("\n⚠️  HOLD CYKLEN STILLE I 3 SEKUNDER...")
time.sleep(3)
mpu.calibrate(samples=20, lcd=lcd.lcd if lcd.available else None)

# GPS state
gps_lat = None
gps_lon = None
last_alarm_telemetry = 0

# ===================== MAIN LOOP =====================
while True:
    now = time.ticks_ms()

    # Check RPC commands
    tb.check_messages()
    
    # Check ESP-NOW data
    espnow.receive()
    
    # ---------- LCD ROTATION & UPDATE ----------
    LCD_ROTATION_INTERVAL = 5000

    if time.ticks_diff(now, last_lcd_rotation) > LCD_ROTATION_INTERVAL:
        lcd_screen = (lcd_screen + 1) % 3
        last_lcd_rotation = now
        last_lcd_update = 0

    if time.ticks_diff(now, last_lcd_update) > LCD_UPDATE_INTERVAL:
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
        except:
            temp = None
            hum = None
        
        stats = power.get_power_stats()
        runtime = stats["runtime_hours"]
        runtime_str = f"{runtime:.1f}h" if runtime else "N/A"
        
        ldr_val = ldr.read() >> 4
        brightness = (pot.read() * 100) // 4095
        
        if lcd_screen == 0:
            lcd.show_status_screen(system_enabled, auto_armed, light_on, 
                                   stats["battery_pct"], temp)
        elif lcd_screen == 1:
            lcd.show_power_screen(stats["battery_pct"], temp, hum, runtime_str)
        elif lcd_screen == 2:
            lcd.show_gps_screen(gps_lat, gps_lon, ldr_val, brightness, 360, 1080)
        
        last_lcd_update = now

    # ---------- MOTION ----------
    if system_enabled and mpu.available:
        motion_detected = mpu.detect_motion()
        
        if motion_detected:
            if time.ticks_diff(now, last_motion_trigger) > MOTION_DEBOUNCE:
                last_motion = now
                last_motion_trigger = now
                
                if auto_armed and not alarm_active:
                    alarm_active = True
                    alarm_led.value(1)
                    neopixel.set_red()
                    print("🚨 ALARM TRIGGERED!")
        
        # Auto-arm efter 30 sek uden bevægelse
        if not auto_armed and time.ticks_diff(now, last_motion) > IDLE_TIME:
            auto_armed = True
            neopixel.clear()
            print("✓ System AUTO-ARMED after 30 seconds idle")
            print(f"baseline={mpu.baseline:.0f} threshold={mpu.motion_threshold}")

    # ---------- ALARM BUZZER ----------
    if alarm_active:
        if buzzer_pwm is None:
            buzzer_pwm = PWM(buzzer_pin, freq=2000, duty=512)
    else:
        if buzzer_pwm is not None:
            buzzer_pwm.deinit()
            buzzer_pwm = None
            buzzer_pin.value(0)

    # ---------- TELEMETRY ----------
    if time.ticks_diff(now, last_telemetry) > TELEMETRY_INTERVAL:
        gps_lat, gps_lon = espnow.get_gps()
        rear_battery = espnow.get_battery()
        
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
        except:
            temp = None
            hum = None

        stats = power.get_power_stats()

        telemetry_data = {
            "temp": temp,
            "humidity": hum,
            "battery": stats["battery_pct"],
            "current": stats["current_ma"],
            "runtime": stats["runtime_hours"],
            "armed": auto_armed,
            "alarm": alarm_active,
            "rear_battery": rear_battery,
            "lat": gps_lat if gps_lat else 0.0,
            "lon": gps_lon if gps_lon else 0.0,
            "free_mem": gc.mem_free()
        }
        
        success = tb.send_telemetry(telemetry_data)
        
        # ALTID opdater last_telemetry - ellers stopper loop
        last_telemetry = now
        
        if success and gps_lat is not None:
            print(f"📡 GPS sent: {gps_lat:.5f}, {gps_lon:.5f}")
        
        # Memory management
        if gc.mem_free() < 50000:
            gc.collect()
            print(f"⚠️ Low RAM: {gc.mem_free()} bytes")

    # ---------- ALARM TELEMETRY (EKSTRA GPS) ----------
    if alarm_active and time.ticks_diff(now, last_alarm_telemetry) > ALARM_TELEMETRY_INTERVAL:
        if gps_lat is not None:
            tb.send_telemetry({
                "alarm": True,
                "lat": gps_lat,
                "lon": gps_lon
            })
            print(f"🚨 Alarm GPS: {gps_lat:.5f}, {gps_lon:.5f}")
        last_alarm_telemetry = now
        
    time.sleep(0.05)