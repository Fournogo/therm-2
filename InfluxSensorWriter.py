#!/usr/bin/env python3
"""
Async InfluxDB sensor data writer using the new async device library
"""

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision
import time
import datetime
import asyncio
import aiohttp
from ConfigLoader import create_device_controller

class AsyncInfluxSensorWriter:
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
        
        # Controller will be initialized in async context
        self.controller = None
        
        # Configuration for sensor readings and external APIs
        self.sensor_configs = self._setup_sensor_configs()
        self.external_api_configs = self._setup_external_api_configs()
        
    async def initialize(self):
        """Initialize the async controller"""
        print("Initializing async device controller...")
        self.controller = await create_device_controller(
            '/home/scrumpi/containers/therm-2/configs', 
            component_path='/home/scrumpi/containers/therm-2'
        )
        print("✅ Controller initialized")
        
    def _setup_sensor_configs(self):
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
            # {
            #     'command_path': 'hvac.temp_sensor.read',
            #     'command_args': {'units': 'f'},  # Arguments for the read command
            #     'influx_fields': {
            #         'temperature': 'hvac_temp',  # status_data['temperature'] -> influx field 'hvac_temp'
            #         'humidity': 'hvac_hum'       # status_data['humidity'] -> influx field 'hvac_hum'
            #     },
            #     'wait_method': 'read_status',    # Wait for this status method
            #     'timeout': 10,
            #     'location_tag': 'hvac_system'
            # },
            # Add more sensor configurations here...
            {
                'command_path': 'averys_room.temp_sensor.read_temp',
                'command_args': {},
                'influx_fields': {
                    'sensor_0.temperature': 'shroompi_temp_0',
                    'sensor_0.humidity': 'shroompi_hum_0',
                    'sensor_1.temperature': 'shroompi_temp_1',
                    'sensor_1.humidity': 'shroompi_hum_1',
                },
                'wait_method': 'temp_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            },
            {
                'command_path': 'ryans_room.temp_sensor.read_temp',
                'command_args': {},
                'influx_fields': {
                    'temperature': 'ems2_temp',
                    'humidity': 'ems2_hum'
                },
                'wait_method': 'temp_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            },
            {
                'command_path': 'hvac.temp_sensor.read_temp',
                'command_args': {},
                'influx_fields': {
                    'temperature': 'fan_temp',
                    'humidity': 'fan_hum'
                },
                'wait_method': 'temp_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            },
            {
                'command_path': 'living_room.temp_sensor.read_temp',
                'command_args': {},
                'influx_fields': {
                    'temperature': 'temperature',
                    'humidity': 'humidity'
                },
                'wait_method': 'temp_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            },
            {
                'command_path': 'living_room.pressure_sensor.read_baro',
                'command_args': {},
                'influx_fields': {
                    'pressure': 'pressure'
                },
                'wait_method': 'baro_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            },
            {
                'command_path': 'hvac.fan.read_fan',
                'command_args': {},
                'influx_fields': {
                    'power': 'fan_power'
                },
                'wait_method': 'fan_status',
                'timeout': 5,
                'location_tag': 'server_closet'
            }
        ]
    
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
            # {
            #     'name': 'thermostat',
            #     'url': 'http://localhost:5023/state',
            #     'method': 'GET',
            #     'timeout': 2,
            #     'max_attempts': 3,
            #     'influx_fields': {
            #         'set_temp': 'thermostat_set_temp',       # Simple field: JSON['set_temp']
            #         # Add more fields as needed:
            #         # 'current_temp': 'thermostat_current_temp',
            #         # 'mode': 'thermostat_mode',
            #         # 'fan_status': 'thermostat_fan_status'
            #     }
            # },
            # {
            #     'name': 'multi_sensor_device',
            #     'url': 'http://your-device/sensors',
            #     'method': 'GET', 
            #     'timeout': 5,
            #     'max_attempts': 2,
            #     'influx_fields': {
            #         # Nested field access using dot notation:
            #         'sensor_0.temperature': 'sensor_0_temp',         # JSON['sensor_0']['temperature']
            #         'sensor_0.humidity': 'sensor_0_humidity',        # JSON['sensor_0']['humidity'] 
            #         'sensor_1.temperature': 'sensor_1_temp',         # JSON['sensor_1']['temperature']
            #         'sensor_1.humidity': 'sensor_1_humidity',        # JSON['sensor_1']['humidity']
            #         # You can go deeper: 'device.status.sensors.0.temp': 'deep_sensor_temp'
            #     }
            # }
            # Add more external APIs here...
        ]
    
    async def _execute_sensor_command(self, command_path, command_args=None):
        """Execute a sensor command using dot notation (now async)"""
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
            
            # Execute the command with arguments (now async)
            if command_args:
                return await method(**command_args)
            else:
                return await method()
                
        except Exception as e:
            print(f"Error executing command {command_path}: {e}")
            return None
    
    async def _wait_for_sensor_data(self, command_path, wait_method, timeout):
        """Wait for sensor data after command execution (now async)"""
        try:
            # Parse the command path to get component
            parts = command_path.split('.')
            device_name = parts[0]
            component_name = parts[1]
            
            device = getattr(self.controller, device_name)
            component = getattr(device, component_name)
            
            # Use the new async execute_and_wait_for_status method
            # This replaces the old wait_for_status + get_latest_status + clear_status_event pattern
            status_data = await component.execute_and_wait_for_status(
                None,  # No command to execute (already executed above)
                wait_method,
                timeout=timeout
            )
            
            return status_data
                
        except Exception as e:
            print(f"Error waiting for {command_path} data: {e}")
            return None
    
    async def read_all_sensors(self):
        """Read data from all configured sensors (now async)"""
        current_time = datetime.datetime.utcnow().isoformat() + "Z"
        all_sensor_data = {}
        
        print(f"Reading sensor data at {current_time}")
        
        # Create tasks for concurrent sensor reading
        tasks = []
        for config in self.sensor_configs:
            task = asyncio.create_task(self._read_single_sensor(config))
            tasks.append((config, task))
        
        # Wait for all sensor readings to complete
        for config, task in tasks:
            try:
                sensor_data = await task
                if sensor_data:
                    all_sensor_data.update(sensor_data)
            except Exception as e:
                print(f"Error reading sensor {config['command_path']}: {e}")
        
        return all_sensor_data, current_time
    
    async def _read_single_sensor(self, config):
        """Read data from a single sensor configuration"""
        command_path = config['command_path']
        print(f"Reading {command_path}...")
        
        sensor_data = {}
        
        try:
            # Execute the sensor read command
            await self._execute_sensor_command(
                command_path, 
                config.get('command_args', {})
            )
            
            # Wait for the status data using the new async method
            parts = command_path.split('.')
            device_name = parts[0]
            component_name = parts[1]
            
            device = getattr(self.controller, device_name)
            component = getattr(device, component_name)
            
            # Use execute_and_wait_for_status with no command (since we already executed above)
            # Or better yet, combine the command execution and waiting:
            method_name = parts[2]
            status_data = await component.execute_and_wait_for_status(
                method_name,
                config['wait_method'],
                timeout=config['timeout'],
                **config.get('command_args', {})
            )
            
            if status_data:
                # Map the status data to InfluxDB field names (supports nested paths)
                for status_key_path, influx_field in config['influx_fields'].items():
                    # Use dot notation for nested access: 'sensor_0.temperature'
                    value = self._get_nested_value(status_data, status_key_path)
                    
                    if value is not None:
                        sensor_data[influx_field] = value
                        print(f"  {status_key_path}: {value} -> {influx_field}")
                    else:
                        print(f"  Warning: {status_key_path} not found in status data")
                        print(f"    Available keys: {list(status_data.keys()) if isinstance(status_data, dict) else 'Not a dict'}")
            else:
                print(f"  Failed to get data from {command_path}")
                
        except Exception as e:
            print(f"Error reading {command_path}: {e}")
            
        return sensor_data
    
    def _get_nested_value(self, data, key_path):
        """
        Get a value from nested dictionary using dot notation
        
        Args:
            data: The dictionary to search
            key_path: Dot notation path like 'sensor_0.temperature' or 'settings.hvac.mode'
            
        Returns:
            The value if found, None if not found
            
        Examples:
            data = {'sensor_0': {'temperature': 73.2, 'humidity': 56.5}}
            get_nested_value(data, 'sensor_0.temperature')  # Returns 73.2
            get_nested_value(data, 'sensor_0.humidity')     # Returns 56.5
            get_nested_value(data, 'sensor_0.missing')      # Returns None
            get_nested_value(data, 'missing.key')           # Returns None
        """
        try:
            keys = key_path.split('.')
            current = data
            
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return None
                    
            return current
        except Exception:
            return None
    
    async def get_external_data(self):
        """Get data from all configured external sources (now async)"""
        external_data = {}
        
        print("Reading external API data...")
        
        # Create tasks for concurrent API calls
        tasks = []
        for config in self.external_api_configs:
            task = asyncio.create_task(self._call_single_api(config))
            tasks.append((config, task))
        
        # Wait for all API calls to complete
        for config, task in tasks:
            try:
                api_data = await task
                if api_data:
                    external_data.update(api_data)
            except Exception as e:
                print(f"Error calling {config['name']} API: {e}")
        
        return external_data
    
    async def _call_single_api(self, config):
        """Call a single external API"""
        name = config['name']
        print(f"Calling {name} API...")
        
        api_data = {}
        
        try:
            # Call the API using aiohttp
            api_response = await self._call_external_api_async(config)
            
            if api_response:
                # Map the JSON response to InfluxDB field names (supports nested paths)
                for json_key_path, influx_field in config['influx_fields'].items():
                    # Use dot notation for nested access: 'sensor_0.temperature'
                    value = self._get_nested_value(api_response, json_key_path)
                    
                    if value is not None:
                        api_data[influx_field] = value
                        print(f"  {json_key_path}: {value} -> {influx_field}")
                    else:
                        print(f"  Warning: {json_key_path} not found in {name} response")
            else:
                print(f"  Failed to get data from {name}")
                
        except Exception as e:
            print(f"Error calling {name}: {e}")
            
        return api_data
    
    async def _call_external_api_async(self, config):
        """Make an async HTTP call to an external API"""
        try:
            timeout = aiohttp.ClientTimeout(total=config.get('timeout', 5))
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if config['method'].upper() == 'GET':
                    async with session.get(config['url']) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            print(f"API {config['name']} returned status {response.status}")
                            return None
                elif config['method'].upper() == 'POST':
                    async with session.post(config['url']) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            print(f"API {config['name']} returned status {response.status}")
                            return None
                else:
                    print(f"Unsupported HTTP method: {config['method']}")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"Timeout calling {config['name']} API")
            return None
        except Exception as e:
            print(f"Error calling {config['name']} API: {e}")
            return None
    
    def write_to_influx(self, sensor_data, external_data, timestamp):
        """Write all collected data to InfluxDB (kept synchronous)"""
        
        # Combine all data
        all_data = {
            **sensor_data,
            **external_data,
            "time": timestamp
        }
        
        # Create the InfluxDB point
        point_data = {
            "name": "sensor_shtc3",  # Measurement name
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
    
    async def run_data_collection(self):
        """Main method to collect and write all sensor data (now async)"""
        try:
            print("=== Starting Async Sensor Data Collection ===")
            
            # Initialize controller
            await self.initialize()
            
            # Read all sensor data concurrently
            sensor_data, timestamp = await self.read_all_sensors()
            
            # Get external data concurrently
            external_data = await self.get_external_data()
            
            # Write to InfluxDB (still synchronous)
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
            if self.controller:
                await self.controller.disconnect_all()

async def main():
    """Main async function for standalone execution"""
    writer = AsyncInfluxSensorWriter()
    await writer.run_data_collection()

if __name__ == "__main__":
    asyncio.run(main())