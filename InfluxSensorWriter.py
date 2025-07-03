#!/usr/bin/env python3
"""
Clean InfluxDB sensor data writer using the new device library
"""

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision
import time
import datetime
from ConfigLoader import create_device_controller
import requests

class InfluxSensorWriter:
    def __init__(self):
        # InfluxDB Configuration (from your original script)
        self.bucket = "temp"
        self.org = "scrumpi"
        self.token = "AEN4fx-48ExWk12GgGXG31Vo7vhmRYTKQfGCGZJem3_uY7Y2Y2HrzexUf35FM_XOrlyqvaQDmNqrJi0qyKPyvQ=="
        self.url = "http://localhost:8086"
        
        # Setup InfluxDB client
        self.client = influxdb_client.InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        
        # Setup device controller
        self.controller = create_device_controller('configs', component_path='.')
        
        # Configuration for sensor readings and external APIs
        self.sensor_configs = self._setup_sensor_configs()
        self.external_api_configs = self._setup_external_api_configs()
        
    def _setup_external_api_configs(self):
        """
        Configure external API calls and how to map their data to InfluxDB
        
        ADD YOUR EXTERNAL API CONFIGURATIONS HERE:
        Format: {
            'name': 'friendly_name',
            'url': 'http://endpoint',
            'method': 'GET' or 'POST',
            'timeout': seconds,
            'influx_fields': {
                'json_key_path': 'influx_field_name',
                'set_temp': 'thermostat_set_temp',                    # Simple key
                'sensor_0.temperature': 'temp_sensor_0',             # Nested key
                'settings.hvac.mode': 'hvac_mode'                    # Deep nested key
            }
        }
        """
        return [
            {
                'name': 'thermostat',
                'url': 'http://localhost:5023/state',
                'method': 'GET',
                'timeout': 2,
                'max_attempts': 3,
                'influx_fields': {
                    'set_temp': 'thermostat_set_temp',       # Simple field: JSON['set_temp']
                    # Add more fields as needed:
                    # 'current_temp': 'thermostat_current_temp',
                    # 'mode': 'thermostat_mode',
                    # 'fan_status': 'thermostat_fan_status'
                }
            },
            {
                'name': 'multi_sensor_device',
                'url': 'http://your-device/sensors',
                'method': 'GET', 
                'timeout': 5,
                'max_attempts': 2,
                'influx_fields': {
                    # Nested field access using dot notation:
                    'sensor_0.temperature': 'sensor_0_temp',         # JSON['sensor_0']['temperature']
                    'sensor_0.humidity': 'sensor_0_humidity',        # JSON['sensor_0']['humidity'] 
                    'sensor_1.temperature': 'sensor_1_temp',         # JSON['sensor_1']['temperature']
                    'sensor_1.humidity': 'sensor_1_humidity',        # JSON['sensor_1']['humidity']
                    # You can go deeper: 'device.status.sensors.0.temp': 'deep_sensor_temp'
                }
            }
            # Add more external APIs here...
        ]
        """
        Configure which sensors to read and how to map them to InfluxDB
        
        ADD YOUR SENSOR CONFIGURATIONS HERE:
        Format: {
            'command_path': 'device.component.method',
            'influx_fields': {
                'status_data_key': 'influx_field_name',
                'temperature': 'hvac_temp',
                'humidity': 'hvac_hum'
            },
            'wait_method': 'status_method_name',
            'timeout': seconds,
            'location_tag': 'sensor_location'
        }
        """
        return [
            # Example configuration - UPDATE THESE FOR YOUR ACTUAL SENSORS
            {
                'command_path': 'hvac.temp_sensor.read',
                'command_args': {'units': 'f'},  # Arguments for the read command
                'influx_fields': {
                    'temperature': 'hvac_temp',  # status_data['temperature'] -> influx field 'hvac_temp'
                    'humidity': 'hvac_hum'       # status_data['humidity'] -> influx field 'hvac_hum'
                },
                'wait_method': 'read_status',    # Wait for this status method
                'timeout': 10,
                'location_tag': 'hvac_system'
            },
            # Add more sensor configurations here...
            # {
            #     'command_path': 'bathroom.temp_sensor.read',
            #     'command_args': {'units': 'f'},
            #     'influx_fields': {
            #         'temperature': 'bathroom_temp',
            #         'humidity': 'bathroom_hum'
            #     },
            #     'wait_method': 'read_status',
            #     'timeout': 10,
            #     'location_tag': 'bathroom'
            # },
            # {
            #     'command_path': 'outdoor.weather_station.read',
            #     'command_args': {},
            #     'influx_fields': {
            #         'temperature': 'outdoor_temp',
            #         'humidity': 'outdoor_hum',
            #         'pressure': 'outdoor_pressure'
            #     },
            #     'wait_method': 'read_status',
            #     'timeout': 15,
            #     'location_tag': 'outdoor'
            # }
        ]
    
    def _setup_sensor_configs(self):
        """Get thermostat set temperature (from your original script)"""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                response = requests.get(self.thermostat_url, timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    set_temp = float(data['set_temp'])
                    print(f"Thermostat set temperature: {set_temp}")
                    return set_temp
                else:
                    print(f"Failed to retrieve thermostat data: {response.status_code}")
            except Exception as e:
                print(f"Error getting thermostat data (attempt {attempts + 1}/{max_attempts}): {e}")
            
            attempts += 1
            time.sleep(1)
        
        print("Could not retrieve thermostat data")
        return None
    
    def _execute_sensor_command(self, command_path, command_args=None):
        """Execute a sensor command using dot notation"""
        try:
            # Parse the command path: 'hvac.temp_sensor.read'
            parts = command_path.split('.')
            if len(parts) < 3:
                raise ValueError(f"Invalid command path: {command_path}")
            
            device_name = parts[0]
            component_name = parts[1]
            method_name = parts[2]
            
            # Get the device and component
            device = getattr(self.controller, device_name)
            component = getattr(device, component_name)
            method = getattr(component, method_name)
            
            # Execute the command with arguments
            if command_args:
                return method(**command_args)
            else:
                return method()
                
        except Exception as e:
            print(f"Error executing command {command_path}: {e}")
            return None
    
    def _wait_for_sensor_data(self, command_path, wait_method, timeout):
        """Wait for sensor data after command execution"""
        try:
            # Parse the command path to get component
            parts = command_path.split('.')
            device_name = parts[0]
            component_name = parts[1]
            
            device = getattr(self.controller, device_name)
            component = getattr(device, component_name)
            
            # Wait for the status
            if component.wait_for_status(wait_method, timeout=timeout):
                status_data = component.get_latest_status(wait_method)
                component.clear_status_event(wait_method)
                return status_data
            else:
                print(f"Timeout waiting for {command_path} status")
                return None
                
        except Exception as e:
            print(f"Error waiting for {command_path} data: {e}")
            return None
    
    def read_all_sensors(self):
        """Read data from all configured sensors"""
        current_time = datetime.datetime.utcnow().isoformat() + "Z"
        all_sensor_data = {}
        
        print(f"Reading sensor data at {current_time}")
        
        # Read each configured sensor
        for config in self.sensor_configs:
            command_path = config['command_path']
            print(f"Reading {command_path}...")
            
            # Execute the sensor read command
            self._execute_sensor_command(
                command_path, 
                config.get('command_args', {})
            )
            
            # Wait for the status data
            status_data = self._wait_for_sensor_data(
                command_path,
                config['wait_method'],
                config['timeout']
            )
            
            if status_data:
                # Map the status data to InfluxDB field names
                for status_key, influx_field in config['influx_fields'].items():
                    if status_key in status_data:
                        all_sensor_data[influx_field] = status_data[status_key]
                        print(f"  {status_key}: {status_data[status_key]} -> {influx_field}")
                    else:
                        print(f"  Warning: {status_key} not found in status data")
            else:
                print(f"  Failed to get data from {command_path}")
        
        return all_sensor_data, current_time
    
    def get_external_data(self):
        """Get data from all configured external sources"""
        external_data = {}
        
        print("Reading external API data...")
        
        # Process each configured external API
        for config in self.external_api_configs:
            name = config['name']
            print(f"Calling {name} API...")
            
            # Call the API
            api_response = self._call_external_api(config)
            
            if api_response:
                # Map the JSON response to InfluxDB field names (supports nested paths)
                for json_key_path, influx_field in config['influx_fields'].items():
                    # Use dot notation for nested access: 'sensor_0.temperature'
                    value = self._get_nested_value(api_response, json_key_path)
                    
                    if value is not None:
                        external_data[influx_field] = value
                        print(f"  {json_key_path}: {value} -> {influx_field}")
                    else:
                        print(f"  Warning: {json_key_path} not found in {name} response")
            else:
                print(f"  Failed to get data from {name}")
        
        return external_data
    
    def write_to_influx(self, sensor_data, external_data, timestamp):
        """Write all collected data to InfluxDB"""
        
        # Combine all data
        all_data = {
            **sensor_data,
            **external_data,
            "time": timestamp
        }
        
        # Create the InfluxDB point
        point_data = {
            "name": "sensor_collection",  # Measurement name
            "location": "server_closet",  # Main location tag
            **all_data
        }
        
        # Define which fields are tags vs fields
        tag_keys = ["location"]
        field_keys = [key for key in all_data.keys() if key not in ["name", "location", "time"]]
        
        try:
            p = influxdb_client.Point.from_dict(
                point_data,
                write_precision=WritePrecision.S,
                record_measurement_key="name",
                record_time_key="time",
                record_tag_keys=tag_keys,
                record_field_keys=field_keys
            )
            
            self.write_api.write(bucket=self.bucket, record=p)
            print(f"✅ Successfully wrote {len(field_keys)} fields to InfluxDB")
            return True
            
        except Exception as e:
            print(f"❌ Error writing to InfluxDB: {e}")
            return False
    
    def run_data_collection(self):
        """Main method to collect and write all sensor data"""
        try:
            print("=== Starting Sensor Data Collection ===")
            
            # Read all sensor data
            sensor_data, timestamp = self.read_all_sensors()
            
            # Get external data
            external_data = self.get_external_data()
            
            # Write to InfluxDB
            success = self.write_to_influx(sensor_data, external_data, timestamp)
            
            if success:
                print("=== Data Collection Complete ===")
            else:
                print("=== Data Collection Failed ===")
                
            return success
            
        except Exception as e:
            print(f"Error in data collection: {e}")
            return False
        finally:
            # Clean up
            self.controller.disconnect_all()

def main():
    """Main function for standalone execution"""
    writer = InfluxSensorWriter()
    writer.run_data_collection()

if __name__ == "__main__":
    main()