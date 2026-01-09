
import time
import struct
import urequests
from machine import Pin, ADC, RTC

class LightController:
    def __init__(self, espnow_sender, rear_mac, neopixel_handler, 
                 ldr_pin=36, pot_pin=34):
        
        self.espnow = espnow_sender
        self.rear_mac = rear_mac
        self.neopixel = neopixel_handler
        
        # LDR sensor
        self.ldr = ADC(Pin(ldr_pin))
        self.ldr.atten(ADC.ATTN_11DB)
        
        # Brightness potmeter
        self.pot = ADC(Pin(pot_pin))
        self.pot.atten(ADC.ATTN_11DB)
        
        # Konfiguration
        self.LDR_DARK_THRESHOLD = 100
        self.DARKNESS_DURATION = 5_000  # 5 sek sustained darkness
        self.LIGHT_TIMEOUT = 180_000    # 3 min idle → sluk
        self.LIGHT_OFF_DELAY = 3_000    # 3 sek delay når lyst
        self.API_UPDATE_INTERVAL = 3600_000  # 1 time
        
        # State
        self.light_on = False
        self.dark_start_time = 0
        self.last_light_off_trigger = 0
        self.last_api_update = 0
        
        # Sunrise/Sunset data
        self.sunrise_minutes = 360   # 06:00 default
        self.sunset_minutes = 1080   # 18:00 default
        self.api_available = False
        
        print("✓ LightController initialized")
    
    def read_ldr(self):
        """Læs LDR værdi (0-255)"""
        return self.ldr.read() >> 4
    
    def read_brightness(self):
        """Læs potmeter brightness (0-100%)"""
        return (self.pot.read() * 100) // 4095
    
    def update_sunrise_sunset(self, lat, lon):
        """Hent solopgangs-/solnedgangstider fra API"""
        if lat is None or lon is None:
            return
        
        try:
            url = f"http://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0"
            print(f"📡 Fetching sun times for {lat:.4f}, {lon:.4f}...")
            
            response = urequests.get(url, timeout=5)
            data = response.json()
            response.close()
            
            if data['status'] == 'OK':
                sunrise_utc = data['results']['sunrise'].split('T')[1][:5]
                sunset_utc = data['results']['sunset'].split('T')[1][:5]
                
                sr_h, sr_m = map(int, sunrise_utc.split(':'))
                ss_h, ss_m = map(int, sunset_utc.split(':'))
                
                self.sunrise_minutes = sr_h * 60 + sr_m
                self.sunset_minutes = ss_h * 60 + ss_m
                self.api_available = True
                
                print(f"✓ Sunrise: {sr_h:02d}:{sr_m:02d}, Sunset: {ss_h:02d}:{ss_m:02d} UTC")
                
        except Exception as e:
            print(f"⚠️ API failed: {e}")
            self.api_available = False
    
    def get_current_time_minutes(self):
        """Returner tid i minutter siden midnat (0-1440)"""
        rtc = RTC()
        dt = rtc.datetime()
        return dt[4] * 60 + dt[5]
    
    def is_nighttime(self):
        """Tjek om det er nat baseret på API"""
        if not self.api_available:
            return False
        
        current_min = self.get_current_time_minutes()
        return current_min < self.sunrise_minutes or current_min > self.sunset_minutes
    
    def update(self, time_since_motion, gps_lat=None, gps_lon=None):
        """
        Hovedloop - opdater lys-system
        Returnerer (light_on, ldr_val, brightness)
        """
        now = time.ticks_ms()
        
        # Opdater API hvis GPS tilgængelig
        if gps_lat and time.ticks_diff(now, self.last_api_update) > self.API_UPDATE_INTERVAL:
            self.update_sunrise_sunset(gps_lat, gps_lon)
            self.last_api_update = now
        
        # Læs sensorer
        ldr_val = self.read_ldr()
        brightness = self.read_brightness()
        
        is_dark_ldr = ldr_val < self.LDR_DARK_THRESHOLD
        is_night = self.is_nighttime()
        motion_active = time_since_motion < self.LIGHT_TIMEOUT
        
        is_dark = is_dark_ldr or is_night
        
        # SUSTAINED DARKNESS CHECK
        if is_dark:
            if self.dark_start_time == 0:
                self.dark_start_time = now
                print(f"🌑 Mørke detekteret (LDR={ldr_val})")
            
            darkness_duration = time.ticks_diff(now, self.dark_start_time)
            sustained_dark = darkness_duration > self.DARKNESS_DURATION
            should_light = sustained_dark and motion_active
            
        else:
            if self.dark_start_time != 0:
                print(f"☀️ Lyst igen (LDR={ldr_val})")
            self.dark_start_time = 0
            should_light = False
        
        # Håndter lys tænd/sluk
        if self.light_on and not should_light:
            if self.last_light_off_trigger == 0:
                self.last_light_off_trigger = now
            
            if time.ticks_diff(now, self.last_light_off_trigger) > self.LIGHT_OFF_DELAY:
                reason = "Lyst igen" if not is_dark else "Ingen bevægelse 3 min"
                print(f"💡 LYS SLUKKET: {reason}")
                self.light_on = False
                self.last_light_off_trigger = 0
                self.dark_start_time = 0
                
                self.neopixel.clear()
                self._send_to_rear(ldr_val, brightness, False)
        
        elif should_light:
            self.last_light_off_trigger = 0
            
            if not self.light_on:
                mode = "LDR mørkt" if is_dark_ldr else "Nat-tid"
                duration = time.ticks_diff(now, self.dark_start_time) / 1000
                print(f"💡 LYS TÆNDT: {mode} i {duration:.1f}s, {brightness}%")
                self.light_on = True
            
            self.neopixel.set_white(brightness)
            self._send_to_rear(ldr_val, brightness, True)
        
        return self.light_on, ldr_val, brightness
    
    def _send_to_rear(self, ldr_val, brightness, light_on):
        """Send ESP-NOW kommando til bagpå"""
        msg = struct.pack('HBB', ldr_val, brightness, 1 if light_on else 0)
        try:
            self.espnow.send(self.rear_mac, msg)
        except:
            pass
    
    def get_sun_times(self):
        """Returner (sunrise_min, sunset_min) for LCD"""
        return self.sunrise_minutes, self.sunset_minutes