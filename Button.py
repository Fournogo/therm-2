import RPi.GPIO as GPIO
import time
from Component import Component, status
from GPIOManager import GPIOManager

class Button(Component):
    def __init__(self, pin, pull_up=True, name=None, device_name=None):

        self.pin = pin
        self.manager = GPIOManager()
        self.manager.reserve_pin(pin)
    
        super().__init__(name, device_name)
        self.pull_up = pull_up
        self.press_count = 0
        self.last_press_time = None
        
        pull = GPIO.PUD_UP if pull_up else GPIO.PUD_DOWN
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=pull)
        
        GPIO.add_event_detect(self.pin, GPIO.FALLING, 
                            callback=self._button_pressed, 
                            bouncetime=200)
    
    def _button_pressed(self, channel):
        """Handle physical button press"""
        self.press_count += 1
        self.last_press_time = time.time()
        
        # Trigger the normal event system
        self.trigger_event('pressed')
        
        # Auto-publish any status methods triggered by 'pressed' event
        self.auto_publish_on_event('pressed')
    
    @status(auto_publish=True, trigger_on=['pressed'])
    def pressed_status(self):
        """Status method that publishes when button is pressed"""
        return {
            "event": "pressed",
            "timestamp": time.time(),
            "press_count": self.press_count,
            "pin": self.pin
        }
    
    @status()
    def get_state(self):
        """Get current button state (call manually)"""
        return {
            "is_pressed": self.is_pressed(),
            "press_count": self.press_count,
            "last_press_time": self.last_press_time,
            "pin": self.pin
        }
    
    def is_pressed(self):
        return GPIO.input(self.pin) == GPIO.LOW
    
    def cleanup(self):
        GPIO.remove_event_detect(self.pin)
        self.manager.release_pin(self.pin)