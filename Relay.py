import RPi.GPIO as GPIO
from Component import Component, command
from GPIOManager import GPIOManager
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
    
    @command
    def on(self):
        GPIO.output(self.pin, self.signal_value_on)
        self._state = True
        self.trigger_event('turned_on')
    
    @command
    def off(self):
        GPIO.output(self.pin, self.signal_value_off)
        self._state = False
        self.trigger_event('turned_off')
    
    def toggle(self):
        if self._state:
            self.off()
        else:
            self.on()

    def cleanup(self):
        self.manager.release_pin(self.pin)