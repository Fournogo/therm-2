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

    @command(data_command=True, events=['fan_status'])
    def read_fan(self):
        """Read fan status - triggers auto-publish of fan_status"""
        self.trigger_event('fan_status')  # Fixed: use underscore, not space
        # Remove manual call to fan_status() - let auto-publish handle it
        self.auto_publish_on_event('fan_status')

    @status(auto_publish=True, trigger_on=['fan_status'])  # Fixed: moved trigger_on to decorator
    def fan_status(self):
        """Get current fan state - auto-published when fan_status event occurs"""
        return {
            "event": "fan_status",
            "timestamp": time.time(),
            "power": self.power,
            "voltage": self.voltage  # Added voltage for completeness
        }

    @command()
    def set_voltage(self, voltage):
        self.voltage = voltage
        self.power = self.voltage / 1000
        self.DAC.set_DAC_out_voltage(int(self.voltage), self.channel)

        self.auto_publish_on_event('fan_status')

    @command()
    def set_power(self, power):
        self.power = power
        self.voltage = self.power * 1000
        self.DAC.set_DAC_out_voltage(int(self.voltage), self.channel)

        self.auto_publish_on_event('fan_status')

    def cleanup(self):
        pass