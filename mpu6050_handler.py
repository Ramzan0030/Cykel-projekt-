from machine import I2C, Pin
import math
import time

class MPU6050Handler:
    def __init__(self, i2c, motion_threshold=5000):
        self.MPU_ADDR = 0x68
        self.i2c = i2c
        self.motion_threshold = motion_threshold
        self.available = False

        try:
            time.sleep(0.2)
            devices = self.i2c.scan()
            print("   Available devices:", [hex(d) for d in devices])

            if self.MPU_ADDR not in devices:
                print("⚠️ MPU6050 not found on I2C bus")
                return

            self.i2c.writeto_mem(self.MPU_ADDR, 0x6B, b'\x00')
            time.sleep(0.1)

            self.available = True
            print("✓ MPU6050 initialized")

        except Exception as e:
            print(f"⚠️ MPU6050 init failed: {e}")

    
    def calibrate(self, samples=10, lcd=None):
        """Calibrate baseline with optional LCD feedback"""
        if not self.available:
            print("⚠️ MPU unavailable for calibration")
            return False
        
        print("Calibrating MPU6050...")
        if lcd:
            lcd.clear()
            lcd.putstr("Calibrating MPU...")
            lcd.move_to(0, 1)
            lcd.putstr("Hold still!")
        
        time.sleep(1)
        readings = []
        
        for i in range(samples):
            try:
                data = self.i2c.readfrom_mem(self.MPU_ADDR, 0x3B, 6)
                x = (data[0] << 8) | data[1]
                y = (data[2] << 8) | data[3]
                z = (data[4] << 8) | data[5]
                
                # Convert to signed
                if x > 32767: x -= 65536
                if y > 32767: y -= 65536
                if z > 32767: z -= 65536
                
                magnitude = math.sqrt(x*x + y*y + z*z)
                readings.append(magnitude)
                
                if lcd:
                    lcd.move_to(0, 2)
                    lcd.putstr(f"Sample {i+1}/{samples}   ")
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"⚠️ Calibration read failed: {e}")
        
        if readings:
            self.baseline = sum(readings) / len(readings)
            print(f"✓ MPU baseline: {self.baseline:.0f}")
            
            if lcd:
                lcd.move_to(0, 3)
                lcd.putstr("Calibration OK!")
                time.sleep(1)
            
            return True
        
        return False
    
    def detect_motion(self):
        """Returns True if motion exceeds threshold"""
        if not self.available:
            return False
        
        max_retries = 3
        retry_delay = 0.01
        
        for attempt in range(max_retries):
            try:
                data = self.i2c.readfrom_mem(self.MPU_ADDR, 0x3B, 6)
                x = (data[0] << 8) | data[1]
                y = (data[2] << 8) | data[3]
                z = (data[4] << 8) | data[5]
                
                if x > 32767: x -= 65536
                if y > 32767: y -= 65536
                if z > 32767: z -= 65536
                
                current = math.sqrt(x*x + y*y + z*z)
                diff = abs(current - self.baseline)
                
                return diff > self.motion_threshold
                
            except OSError:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
            except Exception:
                return False
        
        return False