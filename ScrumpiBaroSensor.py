from adafruit_dps310.basic import DPS310
import board
from Component import Component, status, command
import time

class ScrumpiBaroSensor(Component):
    def __init__(self, name=None, device_name=None):
        self._i2c = board.I2C()  
        self._sensor = DPS310(self._i2c)

        self.pressure = 0

        super().__init__(name, device_name)

    @command
    def read(self):
        self.pressure = self._sensor.pressure
        
        self.trigger_event('read')
        
        # Auto-publish any status methods triggered by 'read' event
        self.auto_publish_on_event('read')

    @status(auto_publish=True, trigger_on=['read'])
    def read_status(self):
        """Status method that publishes when sensor read command is received"""
        return {
            "event": "read_status",
            "timestamp": time.time(),
            "pressure": self.pressure
        }
    
    def cleanup(self):
        pass