import adafruit_shtc3
import board
from Component import Component, status, command
import time

class ScrumpiTempSensor(Component):
    def __init__(self, name=None, device_name=None):
        self._i2c = board.I2C()  
        self._sensor = adafruit_shtc3.SHTC3(self._i2c)

        self.temperature = 0.
        self.humidity = 0.

        super().__init__(name, device_name)

    @command
    def read_temp(self, units="f"):
        self.temperature, self.humidity = self._sensor.measurements

        if units == "f" or units == "F":
            self.temperature = self.temperature * 1.8 + 32
        
        self.trigger_event('read_temp')
        
        # Auto-publish any status methods triggered by 'read' event
        self.auto_publish_on_event('read_temp')

    @status(auto_publish=True, trigger_on=['read_temp'])
    def temp_status(self):
        """Status method that publishes when sensor read command is received"""
        return {
            "event": "read_temp",
            "timestamp": time.time(),
            "temperature": self.temperature,
            "humidity": self.humidity
        }
    
    def cleanup(self):
        pass