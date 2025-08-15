
import yaml
import os
import glob
import asyncio
import logging
import sys
from typing import Dict, Any, List, Optional

from ServerMQTTManager import ServerMQTTManager
from MQTTDeviceProxy import MQTTDeviceProxy, MQTTComponentProxy
from ESPHomeComponentAdapter import ESPHomeComponentAdapter
from UnifiedComponentProxy import UnifiedComponentProxy

class ConfigLoader:
    """
    Config loader that properly creates proxies for remote devices
    without instantiating physical components on the server.
    """
    
    def __init__(self, config_directory: str = "configs", component_path: str = "."):
        self.config_directory = config_directory
        self.component_path = component_path
        
        # Add component path for imports (for inspection only)
        if component_path not in sys.path:
            sys.path.insert(0, component_path)
        
        # Track devices and MQTT managers
        self.mqtt_managers = {}  # One per device_prefix
        self.all_devices = {}    # All devices by name
        self._initialized = False
    
    async def initialize(self):
        """Initialize all connections and devices"""
        if self._initialized:
            return
        
        await self.load_all_configs()
        self._initialized = True
        
        logging.info("CleanConfigLoader initialized successfully")
    
    async def load_all_configs(self):
        """Load all config files"""
        if not os.path.exists(self.config_directory):
            logging.error(f"Config directory '{self.config_directory}' not found")
            return
        
        # Find all YAML files
        config_files = glob.glob(os.path.join(self.config_directory, "*.yaml"))
        config_files.extend(glob.glob(os.path.join(self.config_directory, "*.yml")))
        
        logging.info(f"Found {len(config_files)} config files")
        
        for config_file in config_files:
            try:
                await self.load_config_file(config_file)
            except Exception as e:
                logging.error(f"Failed to load config {config_file}: {e}")
    
    async def load_config_file(self, config_file: str):
        """Load a single config file"""
        logging.info(f"Loading config: {config_file}")
        
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        # Get devices config
        devices_config = config.get('devices', {})
        if not devices_config:
            logging.warning(f"No devices found in {config_file}")
            return
        
        # Check if this has MQTT config (for MQTT devices)
        mqtt_config = config.get('mqtt', {})
        
        if mqtt_config:
            # This is an MQTT device config
            await self._load_mqtt_devices(devices_config, mqtt_config)
        else:
            # This might be ESPHome-only config
            await self._load_esphome_devices(devices_config)
    
    async def _load_mqtt_devices(self, devices_config: Dict, mqtt_config: Dict):
        """Load MQTT devices"""
        device_prefix = mqtt_config.get('device_prefix', 'devices')
        
        # Get or create MQTT manager for this prefix
        if device_prefix not in self.mqtt_managers:
            # Ensure broker_host is set
            if 'broker_host' not in mqtt_config:
                mqtt_config['broker_host'] = 'localhost'
            
            mqtt_manager = ServerMQTTManager(mqtt_config)
            self.mqtt_managers[device_prefix] = mqtt_manager
            
            # Connect to MQTT
            connected = await mqtt_manager.connect()
            if not connected:
                logging.error(f"Failed to connect MQTT manager for prefix '{device_prefix}'")
                return
        else:
            mqtt_manager = self.mqtt_managers[device_prefix]
        
        # Create device proxies
        for device_name, device_config in devices_config.items():
            components = device_config.get('components', {})
            
            # Create device proxy
            device_proxy = MQTTDeviceProxy(
                device_name=device_name,
                components_config=components,
                mqtt_manager=mqtt_manager
            )
            
            # Store and add as attribute
            self.all_devices[device_name] = device_proxy
            setattr(self, device_name, device_proxy)
            
            logging.info(f"Created MQTT device proxy: {device_name} (prefix: {device_prefix})")
    
    async def _load_esphome_devices(self, devices_config: Dict):
        """Load ESPHome devices"""
        for device_name, device_config in devices_config.items():
            components = device_config.get('components', {})
            
            # Create a simple device container
            class ESPHomeDevice:
                pass
            
            device = ESPHomeDevice()
            
            for component_name, component_config in components.items():
                if component_config.get('type') == 'ESPHomeACComponent':
                    # Create ESPHome adapter
                    esphome_adapter = ESPHomeComponentAdapter(
                        name=component_name,
                        device_name=device_name,
                        **{k: v for k, v in component_config.items() if k != 'type'}
                    )
                    
                    # Initialize the ESPHome connection
                    success = await esphome_adapter.initialize()
                    if success:
                        setattr(device, component_name, esphome_adapter)
                        logging.info(f"Created ESPHome component: {device_name}.{component_name}")
                    else:
                        logging.error(f"Failed to initialize ESPHome component: {device_name}.{component_name}")
            
            # Store device
            self.all_devices[device_name] = device
            setattr(self, device_name, device)
    
    def get_device(self, name: str):
        """Get a device by name"""
        return self.all_devices.get(name)
    
    def list_all_devices(self):
        """List all devices and their components"""
        print("\n=== All Loaded Devices ===")
        
        for device_name, device in self.all_devices.items():
            print(f"\nDevice: {device_name}")
            
            if isinstance(device, MQTTDeviceProxy):
                # MQTT device
                for comp_name, component in device.components.items():
                    print(f"  - {comp_name} ({component.component_type})")
                    print(f"    Commands: {', '.join(component.command_methods)}")
                    if component.status_methods:
                        print(f"    Status: {', '.join(component.status_methods)}")
            else:
                # ESPHome device
                for attr_name in dir(device):
                    if not attr_name.startswith('_'):
                        component = getattr(device, attr_name)
                        if hasattr(component, 'component_type'):
                            print(f"  - {attr_name} (ESPHome)")
    
    def list_data_commands(self) -> List[Dict[str, Any]]:
        """List all data commands for state manager"""
        commands = []
        
        for device_name, device in self.all_devices.items():
            if isinstance(device, MQTTDeviceProxy):
                # MQTT device
                for comp_name, component in device.components.items():
                    for cmd_name, cmd_info in component.data_commands.items():
                        status_method = cmd_info['status_method']
                        
                        commands.append({
                            "device_name": device_name,
                            "component_name": comp_name,
                            "command_method_name": cmd_name,
                            "status_method_name": status_method,
                            "status_path": f"{device_name}.{comp_name}.{status_method}",
                            "component_path": f"{device_name}.{comp_name}",
                            "component_proxy": component,
                            "type": "mqtt"
                        })
            else:
                # ESPHome device - handle differently
                for attr_name in dir(device):
                    if not attr_name.startswith('_'):
                        component = getattr(device, attr_name)
                        if hasattr(component, 'get_data_commands'):
                            # Let ESPHome adapter provide its data commands
                            esphome_commands = component.get_data_commands()
                            for cmd in esphome_commands:
                                commands.append({
                                    "device_name": device_name,
                                    "component_name": attr_name,
                                    "command_method_name": cmd['command'],
                                    "status_method_name": cmd['status'],
                                    "status_path": f"{device_name}.{attr_name}.{cmd['status']}",
                                    "component_path": f"{device_name}.{attr_name}",
                                    "component_proxy": component,
                                    "type": "esphome"
                                })
        
        return commands
    
    async def send_heartbeat(self, device_prefix: Optional[str] = None):
        """Send heartbeat to devices"""
        if device_prefix:
            # Send to specific prefix
            if device_prefix in self.mqtt_managers:
                await self.mqtt_managers[device_prefix].send_heartbeat()
        else:
            # Send to all
            for manager in self.mqtt_managers.values():
                await manager.send_heartbeat()
    
    async def disconnect_all(self):
        """Disconnect all connections"""
        # Disconnect MQTT managers
        for manager in self.mqtt_managers.values():
            await manager.disconnect()
        
        # Disconnect ESPHome components
        for device in self.all_devices.values():
            if not isinstance(device, MQTTDeviceProxy):
                # ESPHome device
                for attr_name in dir(device):
                    if not attr_name.startswith('_'):
                        component = getattr(device, attr_name)
                        if hasattr(component, 'disconnect'):
                            await component.disconnect()
        
        logging.info("All connections closed")


# Factory function
async def create_device_controller(config_directory: str = "configs", component_path: str = "."):
    """Create and initialize the clean config loader"""
    loader = ConfigLoader(config_directory, component_path)
    await loader.initialize()
    return loader