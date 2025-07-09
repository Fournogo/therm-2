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
        self.humidity = 0  # Add missing attribute
        
        self.DAC = DFRobot_GP8403(int(address, 16))
        self.DAC.begin()
        self.DAC.set_DAC_outrange(OUTPUT_RANGE_10V)
        self.DAC.set_DAC_out_voltage(self.voltage, self.channel)

    @command
    def read_fan(self):
        """Read fan status - triggers auto-publish of fan_status"""
        self.trigger_event('read_fan')  # Fixed: use underscore, not space
        # Remove manual call to fan_status() - let auto-publish handle it
        self.auto_publish_on_event('read_fan')

    @status(auto_publish=True, trigger_on=['read_fan'])  # Fixed: moved trigger_on to decorator
    def fan_status(self):
        """Get current fan state - auto-published when read_fan event occurs"""
        return {
            "event": "read_fan",
            "timestamp": time.time(),
            "power": self.power,
            "voltage": self.voltage  # Added voltage for completeness
        }

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