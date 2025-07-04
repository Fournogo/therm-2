from Component import Component, status, command
from DFRobot import *
import time

class Fan(Component):
    def __init__(self, address=None, channel=None, name=None, device_name=None):
        super().__init__(name, device_name)
        self.address = address
        self.channel = channel
        self.voltage = 0
        self.power = 0
        
        self.DAC = DFRobot_GP8403(int(address, 16))
        self.DAC.begin()
        self.DAC.set_DAC_outrange(OUTPUT_RANGE_10V)
        self.DAC.set_DAC_out_voltage(self.voltage, self.channel)

    @command
    def read_fan(self):
        self.trigger_event('read_fan')
    
    @status(auto_publish=True, trigger_on=['read fan'])
    def read_fan(self):
        """Get current button state (call manually)"""
        return {
            "event": "read_status",
            "timestamp": time.time(),
            "power": self.power
        }

    @status(auto_publish=True, trigger_on=['read'])
    def read_status(self):
        """Get current button state (call manually)"""
        return {
            "event": "read_status",
            "timestamp": time.time(),
            "temperature": self.voltage,
            "humidity": self.humidity
        }
    
    @command
    def read(self):
        self.trigger_event('read')

    @command
    def set_voltage(self, voltage):
        self.voltage = voltage
        self.power = self.voltage / 1000
        self.DAC.set_DAC_out_voltage(int(self.voltage), self.channel)

    @command
    def set_power(self, power):
        self.power = power
        self.voltage = self.power * 1000
        self.DAC.set_DAC_out_voltage(int(self.voltage), self.channel)
    
    def cleanup(self):
        pass