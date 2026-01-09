
from machine import I2C, Pin
from adc_sub import ADC_substitute
from ina219_lib import INA219

class PowerMonitor:
    def __init__(self, i2c, battery_pin=35, ina219_addr=0x40, battery_capacity=2000):
        self.battery_capacity = battery_capacity
        self.current_readings = []
        self.max_readings = 10
        
        
        self.battery_adc = ADC_substitute(battery_pin)
        
        
        self.ina219 = None
        self.ina219_available = False
        
        try:
            self.ina219 = INA219(i2c, ina219_addr)
            self.ina219_available = True
            print("✓ INA219 initialized")
        except Exception as e:
            print(f"⚠️ INA219 not found: {e}")
    
    def read_battery_percentage(self):
        """Read battery percentage (0-100%)"""
        raw_sum = 0
        for _ in range(10):
            raw_sum += self.battery_adc.read_adc()
        raw_adc = raw_sum // 10
        
        voltage_at_pin = (raw_adc / 4095.0) * 3.3
        battery_voltage = voltage_at_pin * 2.0  
        
        
        battery_pct = ((battery_voltage - 3.0) / (4.2 - 3.0)) * 100
        return max(0, min(100, int(battery_pct)))
    
    def read_current(self):
        """Read current in mA with averaging"""
        if not self.ina219_available:
            return 0.0
        
        try:
            current = self.ina219.get_current()
            current = abs(current)
        except OSError:
            
            current = self.current_readings[-1] if self.current_readings else 0.0
        
        self.current_readings.append(current)
        if len(self.current_readings) > self.max_readings:
            self.current_readings.pop(0)
        
        return sum(self.current_readings) / len(self.current_readings)
    
    def calculate_runtime(self, battery_pct, current_ma):
        """Calculate remaining runtime in hours"""
        if current_ma <= 1:
            return None
        
        remaining_capacity = self.battery_capacity * (battery_pct / 100)
        return remaining_capacity / current_ma
    
    def get_power_stats(self):
        """Get all power statistics"""
        battery = self.read_battery_percentage()
        current = self.read_current()
        runtime = self.calculate_runtime(battery, current)
        
        return {
            'battery_pct': battery,
            'current_ma': current,
            'runtime_hours': runtime
        }