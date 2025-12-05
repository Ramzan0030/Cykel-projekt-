
from uthingsboard.client import TBDeviceMqttClient
from time import sleep
from machine import reset, UART, Pin, ADC
import gc
import secrets
from gps_simple import GPS_SIMPLE
import dht

# CONFIGURATION
dht11_pin = 19                          # DHT11 pin
battery_pin = 34                        # Battery measurement pin

# OBJECTS
dht11 = dht.DHT11(Pin(dht11_pin))       # DHT11 object
battery = ADC(Pin(battery_pin))         # Battery ADC
battery.atten(ADC.ATTN_11DB)            # allow higher voltage range

def read_battery():
    raw = battery.read()
    voltage = raw * (3.3 / 4095) * 2     # *2 pga spændingsdeler (juster efter dine modstande)
    percent = min(100, max(0, int((voltage / 4.2) * 100)))
    return percent

gps_port = 2
gps_speed = 9600
uart = UART(gps_port, gps_speed)
gps = GPS_SIMPLE(uart)

def get_lat_lon():
    lat = lon = None
    if gps.receive_nmea_data():
        if gps.get_latitude() != -999.0 and gps.get_longitude() != -999.0 and gps.get_validity() == "A":
            lat = str(gps.get_latitude())
            lon = str(gps.get_longitude())
            return lat, lon
        else:
            print("GPS data not valid")
            return False, False
    else:
        return False, False

client = TBDeviceMqttClient(secrets.SERVER_IP_ADDRESS, access_token=secrets.ACCESS_TOKEN)
client.connect()
print("Connected to ThingsBoard, starting to send and receive data")

while True:
    try:
        # Memory check
        print(f"\n--- SYSTEM ---")
        print(f"Free memory: {gc.mem_free()}")
        if gc.mem_free() < 2000:
            gc.collect()
            print("Garbage collected!")

        # GPS
        lat_lon = get_lat_lon()
        gps_speed_val = gps.get_speed()
        gps_course_val = gps.get_course()
        print("\n--- GPS ---")
        print(f"Latitude: {lat_lon[0]}")
        print(f"Longitude: {lat_lon[1]}")
        print(f"Speed: {gps_speed_val}")
        print(f"Direction: {gps_course_val}")

        # DHT11
        dht11.measure()
        temp_dht = dht11.temperature()
        hum = dht11.humidity()
        print("\n--- DHT11 ---")
        print(f"Temperature: {temp_dht} °C")
        print(f"Humidity: {hum} %")

        # Battery
        battery_pct = read_battery()
        print("\n--- BATTERY ---")
        print(f"Battery: {battery_pct} %")

        # Telemetry dictionary
        telemetry = {
            'latitude': lat_lon[0],
            'longitude': lat_lon[1],
            'speed': gps_speed_val,
            'direction': gps_course_val,
            'battery': battery_pct,
            'temp_dht': temp_dht,
            'humidity': hum
        }

        print("\n--- TELEMETRY ---")
        print(telemetry)

        client.send_telemetry(telemetry)
        sleep(5)   # send telemetry hvert sekund

    except KeyboardInterrupt:
        print("Disconnected!")
        client.disconnect()
        reset()
