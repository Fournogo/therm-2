import RPi.GPIO as GPIO
from Component import Component, command
import threading
import time

class Light(Component):
    def __init__(self, pin, name=None):
        super().__init__(pin, name)
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)
        self._state = False
        self._flash_thread = None
        self._stop_flash = False
    
    def on(self):
        self._stop_flash = True
        GPIO.output(self.pin, GPIO.HIGH)
        self._state = True
        self.trigger_event('turned_on')
    
    def off(self):
        self._stop_flash = True
        GPIO.output(self.pin, GPIO.LOW)
        self._state = False
        self.trigger_event('turned_off')
    
    def toggle(self):
        if self._state:
            self.off()
        else:
            self.on()
    
    def flash(self, duration=3, interval=0.5):
        self._stop_flash = True
        time.sleep(0.1)
        
        self._stop_flash = False
        self._flash_thread = threading.Thread(
            target=self._flash_worker, 
            args=(duration, interval)
        )
        self._flash_thread.start()
    
    def _flash_worker(self, duration, interval):
        end_time = time.time() + duration
        while time.time() < end_time and not self._stop_flash:
            GPIO.output(self.pin, GPIO.HIGH)
            time.sleep(interval)
            if self._stop_flash:
                break
            GPIO.output(self.pin, GPIO.LOW)
            time.sleep(interval)
        
        GPIO.output(self.pin, GPIO.LOW)
        self._state = False