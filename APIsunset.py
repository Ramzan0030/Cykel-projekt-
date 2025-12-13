import urequests
import time
from machine import Pin, RTC
import ntptime

led = Pin(26, Pin.OUT)

print("Henter tid...")
ntptime.settime()
print("Tid hentet!")

print("Starter loop...")

while True:
    try:
        print("Henter soldata...")
        response = urequests.get("http://api.sunrise-sunset.org/json?lat=36.7201600&lng=-4.4203400&date=today")
        print("Soldata hentet!")
        
        data = response.json()
        response.close()
        
        sunset = data['results']['sunset']
        sunrise = data['results']['sunrise']
        print("Solopgang:", sunrise, "Solnedgang:", sunset)
        
        rtc = RTC()
        now = rtc.datetime()
        current_time = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], now[6])
        print("Nuværende tid:", current_time)
        
        if current_time > sunset:
            led.off()
            print("LED Off")
        else:
            led.on()
            print("LED On")
        
        print("Venter 10 min...")
        time.sleep(600)
        
    except Exception as e:
        print("FEJL:", e)
        time.sleep(60)