
from gpio_lcd import GpioLcd
from machine import Pin
import time

class LCDHandler:
    def __init__(self):
        try:
            self.lcd = GpioLcd(
                rs_pin=Pin(27), 
                enable_pin=Pin(25),
                d4_pin=Pin(33), 
                d5_pin=Pin(32), 
                d6_pin=Pin(21), 
                d7_pin=Pin(22),
                num_lines=4, 
                num_columns=20
            )
            self.current_screen = 0
            self.available = True
            print("✓ LCD initialized")
        except Exception as e:
            print(f"⚠️ LCD init failed: {e}")
            self.lcd = None
            self.available = False
    
    def clear(self):
        if self.available:
            time.sleep(0.05)  
            self.lcd.clear()
    
    def write(self, text, line=0, col=0):
        if self.available:
            try:
                self.lcd.move_to(col, line)
                self.lcd.putstr(text[:20])  
            except:
                pass
    
    def show_alarm_screen(self, gps_lat, gps_lon):
        """Display alarm active screen"""
        if not self.available:
            return
        
        self.clear()
        self.write("!!! ALARM AKTIV !!!", 0)
        self.write("THEFT DETECTED!", 1)
        
        if gps_lat is not None:
            self.write(f"{gps_lat:.4f},{gps_lon:.4f}"[:20], 2)
        else:
            self.write("GPS: NO FIX", 2)
        
        self.write("Stop via TB", 3)
    
    def show_status_screen(self, system_enabled, auto_armed, light_on, battery, temp):
        """Display system status (screen 0)"""
        if not self.available:
            return
        
        self.clear()
        self.write("SYSTEM STATUS", 0)
        
        if not system_enabled:
            status = "DISABLED"
        elif auto_armed:
            status = "AUTO-ARMED"
        else:
            status = "ENABLED"
        
        self.write(f"State: {status}", 1)
        light_status = "ON" if light_on else "OFF"
        self.write(f"Light: {light_status}", 2)
        self.write(f"Bat:{battery}% T:{temp}C"[:20], 3)
    
    def show_power_screen(self, battery, temp, humidity, runtime_str):
        """Display power monitor (screen 1)"""
        if not self.available:
            return
        
        self.clear()
        self.write("POWER MONITOR", 0)
        self.write(f"Battery: {battery}%", 1)
        
        temp_str = f"{temp}C" if temp is not None else "N/A"
        humid_str = f"{humidity}%" if humidity is not None else "N/A"
        self.write(f"T:{temp_str} H:{humid_str}", 2)
        self.write(f"Runtime: {runtime_str}", 3)
    
    def show_gps_screen(self, gps_lat, gps_lon, ldr_val, brightness, sunrise_min, sunset_min):
        """Display GPS & light data (screen 2)"""
        if not self.available:
            return
        
        self.clear()
        self.write("GPS & LYS", 0)
        
        if gps_lat is not None:
            self.write(f"{gps_lat:.5f},{gps_lon:.5f}"[:20], 1)
        else:
            self.write("GPS: Waiting...", 1)
        
        self.write(f"LDR:{ldr_val} Br:{brightness}%"[:20], 2)
        self.write(f"Sun:{sunrise_min//60:02d}:{sunrise_min%60:02d}-{sunset_min//60:02d}:{sunset_min%60:02d}"[:20], 3)