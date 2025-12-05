import time
import network
from umqtt.simple import MQTTClient
from machine import UART, I2C, Pin
import math

# Hardware
gps = UART(2, baudrate=9600, tx=17, rx=16)
i2c = I2C(0, scl=Pin(18), sda=Pin(19), freq=100000)
MPU_ADDR = 0x68
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
time.sleep(0.1)

# Indstillinger
WIFI_SSID = "realme GT 5G"
WIFI_PASS = "Stho091069"
TB_TOKEN = "Ctqwsp4GvIZWVD27u4eA"
TB_SERVER = "demo.thingsboard.io"

TRE_MINUTTER = 180
VEDVARENDE_BEVAEGELSE = 5_000
ALARM_TIMEOUT = 30_000
TJEK_INTERVAL = 5_000
GPS_UPDATE_INTERVAL = 30_000

TEST_MODE = False

armed = True
alarm_klar = False
alarm_aktiv = False
alarm_klar_printet = False
sidst_bevaegelse = time.ticks_ms()
sidst_sendt = 0
sidst_gps_update = 0
sidste_bevaegelse_under_alarm = 0
bevaegelse_start = 0
baseline = 0
latest_gps = None

def wifi_connect():
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
        raise Exception("WiFi fejlede")
    
    print("WiFi OK:", wlan.ifconfig()[0])

def tb_connect():
    client = MQTTClient("esp32", TB_SERVER, user=TB_TOKEN, password="", port=1883)
    client.connect()
    print("ThingsBoard OK")
    return client

def init_baseline():
    global baseline
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
    baseline = sum(readings) / 10
    print(f"MPU Baseline: {baseline:.0f}")

def detectMovement():
    global baseline
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
    diff = abs(current - baseline)
    
    if diff > 2000:
        baseline = current
        return True
    return False

def parse_gprmc(sentence):
    parts = sentence.split(',')
    if len(parts) < 8 or parts[2] != 'A':
        return None
    
    lat_raw = parts[3]
    lat_deg = int(lat_raw[:2]) + float(lat_raw[2:]) / 60
    if parts[4] == 'S':
        lat_deg = -lat_deg
    
    lon_raw = parts[5]
    lon_deg = int(lon_raw[:3]) + float(lon_raw[3:]) / 60
    if parts[6] == 'W':
        lon_deg = -lon_deg
    
    return lat_deg, lon_deg

def updateGps():
    global latest_gps
    if gps.any():
        line = gps.readline()
        try:
            decoded = line.decode('ascii').strip()
            if decoded.startswith('$GPRMC'):
                result = parse_gprmc(decoded)
                if result:
                    latest_gps = result
        except:
            pass

def readGps():
    return latest_gps

def gps_valid():
    return latest_gps is not None

def init_gps():
    global latest_gps
    print("Venter på GPS fix...")
    timeout = 60
    
    while latest_gps is None and timeout > 0:
        if gps.any():
            line = gps.readline()
            try:
                decoded = line.decode('ascii').strip()
                if decoded.startswith('$GPRMC'):
                    result = parse_gprmc(decoded)
                    if result:
                        latest_gps = result
                        print(f"GPS fix: {latest_gps}")
                        return
            except:
                pass
        time.sleep(0.1)  # Hurtigere polling
        timeout -= 1
    
    print("⚠️ Ingen GPS - timeout")
    
def sendToThingsBoard(client, lat, lon, alarm):
    payload = '{{"lat": {}, "lon": {}, "theft_suspected": {}}}'.format(
        lat, lon, "true" if alarm else "false"
    )
    client.publish("v1/devices/me/telemetry", payload)
    print("TB:", "ALARM" if alarm else "OK", f"({lat:.5f}, {lon:.5f})")

# Setup
print("\n" + "="*40)
print("NORMAL MODE" if not TEST_MODE else "TEST MODE")
print("="*40)

wifi_connect()
client = tb_connect()
init_baseline()
init_gps()

# Main Loop
while True:
    nu = time.ticks_ms()
    
    if alarm_aktiv or time.ticks_diff(nu, sidst_gps_update) > GPS_UPDATE_INTERVAL:
        updateGps()
        sidst_gps_update = nu
    
    if TEST_MODE and not alarm_aktiv:
        alarm_aktiv = True
        sidste_bevaegelse_under_alarm = nu
        if gps_valid():
            sendToThingsBoard(client, *readGps(), True)
        sidst_sendt = nu
        time.sleep(2)
    
    if not TEST_MODE:
        bevaeget = detectMovement()
        
        if bevaeget:
            sidst_bevaegelse = nu
            if alarm_aktiv:
                sidste_bevaegelse_under_alarm = nu
        
        if armed and not alarm_aktiv and time.ticks_diff(nu, sidst_bevaegelse) > TRE_MINUTTER:
            if not alarm_klar_printet:
                print("⏳ Klar")
                alarm_klar_printet = True
            alarm_klar = True
        #her
        if alarm_klar and bevaeget:
            if bevaegelse_start == 0:
                bevaegelse_start = nu
                print("⏱️ Bekræfter...")
            elif time.ticks_diff(nu, bevaegelse_start) > VEDVARENDE_BEVAEGELSE:
                alarm_aktiv = True
                alarm_klar = False
                alarm_klar_printet = False
                bevaegelse_start = 0
                sidste_bevaegelse_under_alarm = nu
                if gps_valid():
                    lat, lon = readGps()  # Unpack først
                    sendToThingsBoard(client, lat, lon, True)
                sidst_sendt = nu
                print("🚨 ALARM!")
        elif alarm_klar and not bevaeget:
            bevaegelse_start = 0
        
        if alarm_aktiv and time.ticks_diff(nu, sidste_bevaegelse_under_alarm) > ALARM_TIMEOUT:
            alarm_aktiv = False
            alarm_klar = False
            bevaegelse_start = 0
            print("🟢 Reset")
    
    if alarm_aktiv and gps_valid() and time.ticks_diff(nu, sidst_sendt) > 10_000:
        sendToThingsBoard(client, *readGps(), True)
        sidst_sendt = nu
    
    time.sleep_ms(TJEK_INTERVAL)