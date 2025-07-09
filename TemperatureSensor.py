import adafruit_sht31d
import board
from Component import Component, status, command
import time

class TemperatureSensor(Component):
    def __init__(self, name=None, device_name=None):
        self._i2c = board.I2C()  
        self._sensor = adafruit_sht31d.SHT31D(self._i2c)

        self.temperature = 0.
        self.humidity = 0.

        super().__init__(name, device_name)

    @command
    def read(self, units="f"):
        self.temperature = self._sensor.temperature
        self.humidity = self._sensor.relative_humidity

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