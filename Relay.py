import RPi.GPIO as GPIO
from Component import Component, command, status
from GPIOManager import GPIOManager
import time
import logging

class Relay(Component):
    def __init__(self, pin, signal="LOW", name=None, device_name=None):

        self.pin = pin
        self.manager = GPIOManager()
        self.manager.reserve_pin(pin)

        super().__init__(name, device_name)

        if signal == "LOW":
            self.signal_value_off = getattr(GPIO, "HIGH")
            self.signal_value_on = getattr(GPIO, "LOW")
        elif signal == "HIGH":
            self.signal_value_off = getattr(GPIO, "LOW")
            self.signal_value_on = getattr(GPIO, "HIGH")

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, self.signal_value_off)
        self._state = False
    
    @command()
    def on(self):
        GPIO.output(self.pin, self.signal_value_on)
        self._state = True
        self.trigger_event('turned_on')
        
        self.auto_publish_on_event('relay_status')
    
    @command()
    def off(self):
        GPIO.output(self.pin, self.signal_value_off)
        self._state = False
        self.trigger_event('turned_off')

        self.auto_publish_on_event('relay_status')

    @command(data_command=True, events=['relay_status'])
    def read(self):
        self.trigger_event('relay_status')
        
        # Auto-publish any status methods triggered by 'relay_status' event
        self.auto_publish_on_event('relay_status')
    
    @status(auto_publish=True, trigger_on=['relay_status'])
    def relay_status(self):
        """Status method that publishes when sensor read command is received"""
        return {
            "event": "relay_status",
            "timestamp": time.time(),
            "relay": self._state
        }

    def toggle(self):
        if self._state:
            self.off()
        else:
            self.on()

    def cleanup(self):
        self.manager.release_pin(self.pin)