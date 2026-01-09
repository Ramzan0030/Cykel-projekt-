"""
Alarm system med auto-arming og buzzer
"""

import time
from machine import Pin, PWM

class AlarmSystem:
    def __init__(self, mpu_handler, alarm_led_pin=26, buzzer_pin=15):
        
        self.mpu = mpu_handler
        
        # Hardware
        self.alarm_led = Pin(alarm_led_pin, Pin.OUT)
        self.alarm_led.value(0)
        
        self.buzzer_pin = Pin(buzzer_pin, Pin.OUT)
        self.buzzer_pwm = None
        
        # Konfiguration
        self.IDLE_TIME = 180_000  # 3 min til auto-arm
        self.MOTION_DEBOUNCE = 500
        
        # State
        self.system_enabled = True
        self.auto_armed = False
        self.alarm_active = False
        
        self.last_motion = time.ticks_ms()
        self.last_motion_trigger = 0
        
        print("✓ AlarmSystem initialized")
    
    def enable(self):
        """Aktivér system"""
        self.system_enabled = True
        self.alarm_active = False
        self.auto_armed = False
        self.alarm_led.value(0)
        self._stop_buzzer()
        self.last_motion = time.ticks_ms()
    
    def disable(self):
        """Deaktivér system"""
        self.system_enabled = False
        self.alarm_active = False
        self.auto_armed = False
        self.alarm_led.value(0)
        self._stop_buzzer()
    
    def update(self):
        """
        Hovedloop - tjek motion og opdater alarm state
        Returnerer (motion_detected, time_since_motion)
        """
        now = time.ticks_ms()
        motion_detected = False
        
        if not self.system_enabled or not self.mpu.available:
            return False, time.ticks_diff(now, self.last_motion)
        
        # Tjek motion
        motion_detected = self.mpu.detect_motion()
        
        if motion_detected:
            if time.ticks_diff(now, self.last_motion_trigger) > self.MOTION_DEBOUNCE:
                self.last_motion = now
                self.last_motion_trigger = now
                
                # Trigger alarm hvis auto-armed
                if self.auto_armed and not self.alarm_active:
                    self.alarm_active = True
                    self.alarm_led.value(1)
                    self._start_buzzer()
                    print("🚨 ALARM TRIGGERED!")
        
        # Auto-arm efter 3 min idle
        if not self.auto_armed and time.ticks_diff(now, self.last_motion) > self.IDLE_TIME:
            self.auto_armed = True
            print("✓ System AUTO-ARMED after 3 minutes idle")
        
        # Opdater buzzer
        if self.alarm_active:
            if self.buzzer_pwm is None:
                self._start_buzzer()
        else:
            self._stop_buzzer()
        
        time_since_motion = time.ticks_diff(now, self.last_motion)
        return motion_detected, time_since_motion
    
    def _start_buzzer(self):
        """Start alarm buzzer"""
        if self.buzzer_pwm is None:
            self.buzzer_pwm = PWM(self.buzzer_pin, freq=2000, duty=512)
    
    def _stop_buzzer(self):
        """Stop alarm buzzer"""
        if self.buzzer_pwm is not None:
            self.buzzer_pwm.deinit()
            self.buzzer_pwm = None
            self.buzzer_pin.value(0)
    
    def get_status(self):
        """Returner (enabled, auto_armed, alarm_active)"""
        return self.system_enabled, self.auto_armed, self.alarm_active