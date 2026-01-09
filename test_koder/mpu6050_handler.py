from machine import I2C, Pin
import math
import time

class MPU6050Handler:
    def __init__(self, i2c, motion_threshold=5000):
        self.MPU_ADDR = 0x68
        self.i2c = i2c
        self.motion_threshold = motion_threshold
        self.available = False
        self.baseline = 16384  # Default

        try:
            time.sleep(0.2)
            
            # Wake MPU
            for _ in range(3):
                try:
                    self.i2c.writeto_mem(self.MPU_ADDR, 0x6B, b'\x00')
                    time.sleep(0.1)
                    break
                except:
                    time.sleep(0.1)

            self.available = True
            print("✓ MPU6050 initialized")

        except Exception as e:
            print(f"⚠️ MPU6050 init failed: {e}")

    def calibrate(self, samples=10, lcd=None):
        if not self.available:
            return False
        
        print("Calibrating MPU6050...")
        time.sleep(1)
        readings = []
        
        for i in range(samples):
            for attempt in range(5):
                try:
                    time.sleep(0.15)  # Længere delay
                    data = self.i2c.readfrom_mem(self.MPU_ADDR, 0x3B, 6)
                    
                    x = (data[0] << 8) | data[1]
                    y = (data[2] << 8) | data[3]
                    z = (data[4] << 8) | data[5]
                    
                    if x > 32767: x -= 65536
                    if y > 32767: y -= 65536
                    if z > 32767: z -= 65536
                    
                    magnitude = math.sqrt(x*x + y*y + z*z)
                    readings.append(magnitude)
                    break
                    
                except:
                    if attempt == 4:
                        print(f"⚠️ Sample {i+1} skipped")
                    time.sleep(0.2)
        
        if len(readings) >= 5:
            self.baseline = sum(readings) / len(readings)
            print(f"✓ MPU baseline: {self.baseline:.0f} ({len(readings)}/{samples} samples)")
            return True
        
        print("⚠️ Calibration failed")
        return False
    
    def detect_motion(self):
        if not self.available:
            return False
        
        for attempt in range(5):
            try:
                time.sleep(0.05)
                data = self.i2c.readfrom_mem(self.MPU_ADDR, 0x3B, 6)
                
                x = (data[0] << 8) | data[1]
                y = (data[2] << 8) | data[3]
                z = (data[4] << 8) | data[5]
                
                if x > 32767: x -= 65536
                if y > 32767: y -= 65536
                if z > 32767: z -= 65536
                
                current = math.sqrt(x*x + y*y + z*z)
                diff = abs(current - self.baseline)
                
                triggered = diff > self.motion_threshold
                
                if triggered:
                    print(f"🚨 MPU TRIGGER: diff={diff:.0f} > {self.motion_threshold}")
                
                return triggered
                
            except OSError:
                if attempt == 4:
                    print("⚠️ MPU read failed after 5 attempts")
                time.sleep(0.1)
        
        return False  # Alle forsøg fejlede
