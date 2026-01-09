
from machine import Pin
from neopixel import NeoPixel

class NeoPixelHandler:
    def __init__(self, pin=13, num_leds=12, first_led=0):
        self.num_leds = num_leds
        self.first_led = first_led
        self.available = False
        
        try:
            self.np = NeoPixel(Pin(pin), num_leds)
            self.available = True
            self.clear()
            print("✓ NeoPixel initialized")
        except Exception as e:
            print(f"⚠️ NeoPixel init failed: {e}")
            self.np = None
    
    def clear(self):
        """Turn off all LEDs"""
        if not self.available:
            return
        for i in range(self.num_leds):
            self.np[i] = (0, 0, 0)
        self.np.write()
    
    def set_color(self, r, g, b):
        """Set all active LEDs to color"""
        if not self.available:
            return
        
        
        for i in range(self.first_led):
            self.np[i] = (0, 0, 0)
        
       
        for i in range(self.first_led, self.num_leds):
            self.np[i] = (r, g, b)
        
        self.np.write()
    
    def set_white(self, brightness_pct):
        """Set white light with brightness percentage (0-100)"""
        val = int(brightness_pct * 2.55)
        self.set_color(val, val, val)
    
    def set_red(self, brightness=50):
        """Set red color (alarm/rear light)"""
        self.set_color(brightness, 0, 0)
    
    def set_green(self, brightness=20):
        """Set green color (armed/ready)"""
        self.set_color(0, brightness, 0)
    
    def blink(self, r, g, b, on_time=200):
        """Single blink for alarm animations"""
        if not self.available:
            return False
        
        self.set_color(r, g, b)
        return True