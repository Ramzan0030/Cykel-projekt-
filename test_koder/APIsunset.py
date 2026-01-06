import network
import time
from machine import Pin, RTC
import urequests

SSID = "matt"
PASSWORD = "12345678"

led = Pin(26, Pin.OUT)

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
    raise Exception("No WiFi")

print(f"Connected: {sta.ifconfig()[0]}")

while True:
    try:
        response = urequests.get("http://api.sunrise-sunset.org/json?lat=55.6761&lng=12.5683&formatted=0")
        data = response.json()
        response.close()
        
        sunset_utc = data['results']['sunset']
        sunrise_utc = data['results']['sunrise']
        
        sunset_time = sunset_utc.split('T')[1].split('+')[0]
        sunrise_time = sunrise_utc.split('T')[1].split('+')[0]
        
        sunset_h, sunset_m = map(int, sunset_time.split(':')[:2])
        sunrise_h, sunrise_m = map(int, sunrise_time.split(':')[:2])
        
        # Konverter til CET
        sunset_h += 1
        sunrise_h += 1
        
        sunset_min = sunset_h * 60 + sunset_m
        sunrise_min = sunrise_h * 60 + sunrise_m
        
        # Brug RTC direkte (uden offset)
        rtc = RTC()
        now = rtc.datetime()
        current_min = now[4] * 60 + now[5]
        
        is_dark = current_min < sunrise_min or current_min > sunset_min
        led.value(1 if is_dark else 0)
        
        print(f"\nSunrise: {sunrise_h:02d}:{sunrise_m:02d}")
        print(f"Sunset:  {sunset_h:02d}:{sunset_m:02d}")
        print(f"Now:     {now[4]:02d}:{now[5]:02d}")
        print(f"LED {'ON' if is_dark else 'OFF'}")
        
        time.sleep(600)
        
    except Exception as e:
        print(f"ERROR: {e}")
        time.sleep(60)