import adafruit_sht31d
import adafruit_tca9548a
import board
from Component import Component, status, command
import time

class MultiTempSensor(Component):
    def __init__(self, sensor_count=2, name=None, device_name=None):
        self._i2c = board.I2C()
        self._tca = adafruit_tca9548a.TCA9548A(self._i2c)

        self.sensor_count = sensor_count
        self.sensors = []

        for i in range(self.sensor_count):
            self.sensors.append({
                "sensor": adafruit_sht31d.SHT31D(self._tca[i]),
                "temperature": 0.,
                "humidity": 0.,
                })

        super().__init__(name, device_name)

    @command(data_command=True, events=['temp_status'])
    def read_temp(self, units="f"):

        for sensor in self.sensors:
            sensor["temperature"] = sensor["sensor"].temperature
            sensor["humidity"] = sensor["sensor"].relative_humidity

            if units == "f" or units == "F":
                sensor["temperature"] = sensor["temperature"] * 1.8 + 32
        
        self.trigger_event('temp_status')
        
        # Auto-publish any status methods triggered by 'read' event
        self.auto_publish_on_event('temp_status')

    @status(auto_publish=True, trigger_on=['temp_status'])
    def temp_status(self):
        """Status method that publishes when sensor read command is received"""

        result = {
            "event": "temp_status",
            "timestamp": time.time()
        }

        for i in range(len(self.sensors)):
            sensor_name = f"sensor_{i}"
            result[sensor_name] = {
                "temperature": self.sensors[i]["temperature"],
                "humidity": self.sensors[i]["humidity"]
            }

        return result
    
    def cleanup(self):
        pass