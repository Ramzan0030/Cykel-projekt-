import time
import network
from umqtt.simple import MQTTClient
from machine import UART, I2C, Pin, ADC
import math
import dht
import gc
import json

# ============================================================================
# CONFIGURATION
# ============================================================================
# WiFi
WIFI_SSID = "matt"
WIFI_PASS = "12345678"

# ThingsBoard
TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"
TB_SERVER = "demo.thingsboard.io"

# Timing (jf. Krav ID 4)
IDLE_TIME = 180          # 3 min før alarm klar (ms) - Krav ID 4
MOTION_CONFIRM = 1_000       # 1 sek vedvarende bevægelse (ms)
ALARM_TIMEOUT = 10_000       # 10 sek uden bevægelse → reset alarm (ms)
TELEMETRY_INTERVAL = 5_000   # Normal telemetri hver 5. sek (ms) - Krav ID 3
ALARM_TELEMETRY = 10_000     # Under alarm hver 10. sek (ms) - Krav ID 4
GPS_UPDATE = 1_000           # GPS opdatering 1 Hz (ms)

# Hardware pins
GPS_TX = 17
GPS_RX = 16
MPU_SCL = 18
MPU_SDA = 19
DHT11_PIN = 21
BATTERY_PIN = 34

# Test mode
TEST_MODE = False

# ============================================================================
# HARDWARE INIT
# ============================================================================
# GPS
gps = UART(2, baudrate=9600, tx=GPS_TX, rx=GPS_RX)

# MPU6050
i2c = I2C(0, scl=Pin(MPU_SCL), sda=Pin(MPU_SDA), freq=100000)
MPU_ADDR = 0x68
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')  # Wake up MPU
time.sleep(0.1)

# DHT11
dht_sensor = dht.DHT11(Pin(DHT11_PIN))

# Battery ADC
battery_adc = ADC(Pin(BATTERY_PIN))
battery_adc.atten(ADC.ATTN_11DB)

# ============================================================================
# STATE VARIABLES
# ============================================================================
armed = True
alarm_ready = False
alarm_active = False
alarm_ready_printed = False

last_motion = time.ticks_ms()
last_telemetry = 0
last_gps_update = 0
last_alarm_motion = 0
motion_start = 0
mpu_baseline = 0

# GPS data
latest_gps = None
latest_speed = None
latest_course = None
prev_gps = None
prev_fix_time = None

# ============================================================================
# WIFI & MQTT
# ============================================================================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    if wlan.isconnected():
        wlan.disconnect()
        time.sleep(1)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    
    timeout = 10
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
    
    if not wlan.isconnected():
        raise Exception("WiFi connection failed")
    print(f"✓ WiFi connected: {wlan.ifconfig()[0]}")


def on_rpc_request(topic, msg):
    """Handle RPC commands from ThingsBoard"""
    global armed, alarm_ready, alarm_active, alarm_ready_printed, client
    try:
        data = json.loads(msg)
        method = data.get('method')
        
        # Extract request ID from topic
        request_id = topic.decode('utf-8').split('/')[-1]
        
        if method == 'getState':
            # Send current state as response
            response = armed
            client.publish(f'v1/devices/me/rpc/response/{request_id}', 
                          json.dumps(response))
            print(f"Sent state: {armed}")
        
        elif method == 'setState':
            params = data.get('params')
            new_state = params if isinstance(params, bool) else (params == 'true')
            
            if new_state:
                armed = True
                alarm_ready = False
                alarm_active = False
                alarm_ready_printed = False
                print("🟢 SYSTEM ARMED via ThingsBoard")
            else:
                armed = False
                alarm_ready = False
                alarm_active = False
                alarm_ready_printed = False
                print("🔴 SYSTEM DISARMED via ThingsBoard")
            
            # Send success response
            client.publish(f'v1/devices/me/rpc/response/{request_id}', 
                          json.dumps(armed))
    except Exception as e:
        print(f"RPC error: {e}")
def connect_thingsboard():
    global client
    client = MQTTClient("esp32_bike", TB_SERVER, user=TB_TOKEN, password="", port=1883)
    client.set_callback(on_rpc_request)
    client.connect()
    client.subscribe('v1/devices/me/rpc/request/+')
    print("✓ ThingsBoard connected")
    return client

# ============================================================================
# MPU6050 MOTION DETECTION
# ============================================================================
def init_mpu_baseline():
    global mpu_baseline
    readings = []
    for _ in range(10):
        data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
        x = (data[0] << 8) | data[1]
        y = (data[2] << 8) | data[3]
        z = (data[4] << 8) | data[5]
        
        if x > 32767: x -= 65536
        if y > 32767: y -= 65536
        if z > 32767: z -= 65536
        
        readings.append(math.sqrt(x*x + y*y + z*z))
        time.sleep(0.05)
    
    mpu_baseline = sum(readings) / 10
    print(f"✓ MPU baseline: {mpu_baseline:.0f}")


def detect_motion():
    global mpu_baseline
    if TEST_MODE:
        return True
    
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    x = (data[0] << 8) | data[1]
    y = (data[2] << 8) | data[3]
    z = (data[4] << 8) | data[5]
    
    if x > 32767: x -= 65536
    if y > 32767: y -= 65536
    if z > 32767: z -= 65536
    
    current = math.sqrt(x*x + y*y + z*z)
    diff = abs(current - mpu_baseline)
    
    if diff > 2000:
        mpu_baseline = current
        return True
    return False

# ============================================================================
# GPS PARSING
# ============================================================================
def parse_gprmc(sentence):
    """Parse NMEA RMC sentence"""
    parts = sentence.split(',')
    if len(parts) < 9 or parts[2] != 'A':
        return None
    
    # Latitude
    lat_raw = parts[3]
    lat = int(lat_raw[:2]) + float(lat_raw[2:]) / 60
    if parts[4] == 'S':
        lat = -lat
    
    # Longitude
    lon_raw = parts[5]
    lon = int(lon_raw[:3]) + float(lon_raw[3:]) / 60
    if parts[6] == 'W':
        lon = -lon
    
    # Speed (knots → km/h)
    speed = None
    if parts[7]:
        try:
            speed = float(parts[7]) * 1.852
        except:
            pass
    
    # Course
    course = None
    if parts[8]:
        try:
            course = float(parts[8])
        except:
            pass
    
    return lat, lon, speed, course


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS points in km"""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def update_gps():
    """Poll GPS and update latest position/speed"""
    global latest_gps, latest_speed, latest_course, prev_gps, prev_fix_time
    
    if gps.any():
        line = gps.readline()
        try:
            sentence = line.decode('ascii').strip()
            if sentence.startswith('$GPRMC') or sentence.startswith('$GNRMC'):
                result = parse_gprmc(sentence)
                if result:
                    lat, lon, speed, course = result
                    now = time.ticks_ms()
                    
                    latest_gps = (lat, lon)
                    latest_course = course
                    
                    if speed is not None:
                        latest_speed = speed
                    elif prev_gps and prev_fix_time:
                        dt_ms = time.ticks_diff(now, prev_fix_time)
                        if dt_ms > 0:
                            km = haversine_km(prev_gps[0], prev_gps[1], lat, lon)
                            latest_speed = (km * 3600.0) / (dt_ms / 1000.0)
                    
                    prev_gps = (lat, lon)
                    prev_fix_time = now
        except:
            pass


def wait_for_gps():
    """Block until GPS fix acquired"""
    global latest_gps, latest_speed, latest_course
    print("Waiting for GPS fix...")
    
    timeout = 60
    while latest_gps is None and timeout > 0:
        update_gps()
        time.sleep(0.1)
        timeout -= 1
    
    if latest_gps:
        print(f"✓ GPS fix: {latest_gps}, speed: {latest_speed} km/h")
    else:
        print("⚠️ GPS timeout - continuing without fix")

# ============================================================================
# SENSOR READINGS
# ============================================================================
def read_temperature_humidity():
    """Read DHT11 sensor"""
    try:
        dht_sensor.measure()
        temp = dht_sensor.temperature()
        humidity = dht_sensor.humidity()
        return temp, humidity
    except:
        return None, None


def read_battery():
    """Read battery voltage and calculate percentage"""
    raw = battery_adc.read()
    voltage = raw * (3.3 / 4095) * 2
    percent = min(100, max(0, int((voltage / 4.2) * 100)))
    return percent

# ============================================================================
# THINGSBOARD TELEMETRY
# ============================================================================
def send_telemetry(client, alarm=False):
    """Send all sensor data to ThingsBoard"""
    temp, humidity = read_temperature_humidity()
    battery = read_battery()
    
    lat = latest_gps[0] if latest_gps else 0.0
    lon = latest_gps[1] if latest_gps else 0.0
    speed = latest_speed if latest_speed is not None else 0.0
    course = latest_course if latest_course is not None else 0.0
    
    payload = (
        '{{'
        '"latitude":{lat:.6f},'
        '"longitude":{lon:.6f},'
        '"speed_kmh":{spd:.2f},'
        '"direction_deg":{crs:.1f},'
        '"temp_dht":{temp},'
        '"humidity":{hum},'
        '"battery_pct":{bat},'
        '"theft_alarm":{alarm},'
        '"system_armed":{armed},'
        '"free_memory":{mem}'
        '}}'
    ).format(
        lat=lat, lon=lon, spd=speed, crs=course,
        temp=temp if temp else 'null',
        hum=humidity if humidity else 'null',
        bat=battery,
        alarm='true' if alarm else 'false',
        armed='true' if armed else 'false',
        mem=gc.mem_free()
    )
    
    client.publish("v1/devices/me/telemetry", payload)
    
    status = "🚨 ALARM" if alarm else ("🟢 ARMED" if armed else "🔴 DISARMED")
    print(f"{status} | GPS: ({lat:.5f}, {lon:.5f}) | Speed: {speed:.1f} km/h | "
          f"Temp: {temp}°C | Battery: {battery}% | Mem: {gc.mem_free()}")

# ============================================================================
# MAIN PROGRAM
# ============================================================================
print("\n" + "="*50)
print("SMART BICYCLE SYSTEM - TEST MODE" if TEST_MODE else "SMART BICYCLE SYSTEM")
print("="*50)

# Connect
connect_wifi()
client = connect_thingsboard()

# Initialize sensors
init_mpu_baseline()
wait_for_gps()

print("\n🚴 System running...\n")
print("💡 Use ThingsBoard Power button to ARM/DISARM system\n")

# Main loop
while True:
    now = time.ticks_ms()
    
    # Check for RPC messages from ThingsBoard
    try:
        client.check_msg()
    except:
        pass
    
    # GPS update (1 Hz)
    if time.ticks_diff(now, last_gps_update) > GPS_UPDATE:
        update_gps()
        last_gps_update = now
    
    # Memory management
    if gc.mem_free() < 2000:
        gc.collect()
    
    # TEST MODE: Trigger immediate alarm
    if TEST_MODE and not alarm_active:
        alarm_active = True
        last_alarm_motion = now
        if latest_gps:
            send_telemetry(client, alarm=True)
            last_telemetry = now
        time.sleep(2)
    
    # NORMAL MODE: Theft detection logic (only if armed)
    if not TEST_MODE and armed:
        motion = detect_motion()
        
        if motion:
            last_motion = now
            if alarm_active:
                last_alarm_motion = now
        
        # Become ready after idle period
        if not alarm_active and time.ticks_diff(now, last_motion) > IDLE_TIME:
            if not alarm_ready_printed:
                print("⏳ Alarm ready - waiting for motion...")
                alarm_ready_printed = True
            alarm_ready = True
        
        # Confirm sustained motion before triggering
        if alarm_ready and motion:
            if motion_start == 0:
                motion_start = now
                print("⏱️ Confirming motion...")
            elif time.ticks_diff(now, motion_start) > MOTION_CONFIRM:
                alarm_active = True
                alarm_ready = False
                alarm_ready_printed = False
                motion_start = 0
                last_alarm_motion = now
                
                if latest_gps:
                    send_telemetry(client, alarm=True)
                    last_telemetry = now
                print("🚨 THEFT ALARM ACTIVATED!")
        elif alarm_ready and not motion:
            motion_start = 0
        
        # Reset alarm if no motion
        if alarm_active and time.ticks_diff(now, last_alarm_motion) > ALARM_TIMEOUT:
            alarm_active = False
            alarm_ready = False
            motion_start = 0
            print("🟢 Alarm reset\n")
    
    # Send periodic telemetry
    interval = ALARM_TELEMETRY if alarm_active else TELEMETRY_INTERVAL
    if latest_gps and time.ticks_diff(now, last_telemetry) > interval:
        send_telemetry(client, alarm=alarm_active)
        last_telemetry = now
    
    time.sleep_ms(100)