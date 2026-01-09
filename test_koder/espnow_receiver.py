
import network
import espnow
import struct
import time

class ESPNowReceiver:
    def __init__(self, rear_mac=b'\x68\x25\xDD\xE9\xB7\xD8'):
        self.rear_mac = rear_mac
        self.gps_lat = None
        self.gps_lon = None
        self.rear_battery = None
        self.last_gps_print = 0
        
        try:
            
            self.sta = network.WLAN(network.STA_IF)
            self.e = espnow.ESPNow()
            self.e.active(True)
            
            
            print("✓ ESP-NOW initialized (passive mode)")
        except Exception as e:
            print(f"⚠️ ESP-NOW init failed: {e}")
            self.e = None
    
    def receive(self):
        """Check for incoming GPS/battery data"""
        if self.e is None:
            return False
        
        received = False
        
        while True:
            try:
                host, msg = self.e.recv(0)  
            except:
                break
            
            if msg is None:
                break
            
            
            if len(msg) == 8:
                try:
                    lat, lon = struct.unpack('ff', msg)
                    
                    if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                        self.gps_lat = lat
                        self.gps_lon = lon
                        received = True
                        
                        now = time.ticks_ms()
                        if time.ticks_diff(now, self.last_gps_print) > 5000:
                            print(f"📍 GPS: {self.gps_lat:.6f}, {self.gps_lon:.6f}")
                            self.last_gps_print = now
                except:
                    pass
            
            
            elif len(msg) == 1:
                try:
                    self.rear_battery = struct.unpack('B', msg)[0]
                except:
                    pass
        
        return received
    
    def get_gps(self):
        """Get current GPS coordinates"""
        return self.gps_lat, self.gps_lon
    
    def get_battery(self):
        """Get rear battery percentage"""
        return self.rear_battery