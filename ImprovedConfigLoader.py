# ImprovedConfigLoader.py
import yaml
import os
import glob
import asyncio
import logging
from typing import Dict, Any, List, Optional

from BaseComponent import BaseComponent
from MQTTComponentAdapter import MQTTComponentAdapter
from ESPHomeComponentAdapter import ESPHomeComponentAdapter
from UnifiedComponentProxy import UnifiedComponentProxy
from ServerDeviceProxy import AsyncServerDeviceManager

# Import ComponentFactory for MQTT components
try:
    from ComponentFactory import ComponentFactory
except ImportError:
    logging.warning("ComponentFactory not found, MQTT components may not work")
    ComponentFactory = None

class ImprovedConfigLoader:
    """
    Simplified config loader that creates unified component proxies
    for both MQTT and ESPHome components.
    """
    
    def __init__(self, config_directory: str = "configs", component_path: str = "."):
        self.config_directory = config_directory
        self.component_path = component_path
        self.devices = {}
        self.mqtt_managers = {}  # One per device_prefix
        self._initialized = False
        
        # Add component path for imports
        if component_path not in os.sys.path:
            os.sys.path.insert(0, component_path)
    
    async def initialize(self):
        """Initialize all components and connections"""
        if self._initialized:
            return
        
        # Load all config files
        await self.load_all_configs()
        
        # Initialize all components
        await self._initialize_all_components()
        
        self._initialized = True
        logging.info("ImprovedConfigLoader initialized successfully")
    
    async def load_all_configs(self):
        """Load all YAML config files"""
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
                logging.error(f"Failed to load config file {config_file}: {e}")
    
    async def load_config_file(self, config_file: str):
        """Load a single config file"""
        logging.info(f"Loading config: {config_file}")
        
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        # Check if this has MQTT config
        mqtt_config = config.get('mqtt', {})
        mqtt_manager = None
        
        if mqtt_config:
            # Get or create MQTT manager for this prefix
            device_prefix = mqtt_config.get('device_prefix', 'devices')
            
            if device_prefix not in self.mqtt_managers:
                # Ensure broker_host is set
                if 'broker_host' not in mqtt_config:
                    mqtt_config['broker_host'] = 'localhost'
                    logging.info(f"Using default broker_host 'localhost' for prefix '{device_prefix}'")
                
                mqtt_manager = AsyncServerDeviceManager(mqtt_config)
                self.mqtt_managers[device_prefix] = mqtt_manager
                
                # Initialize MQTT connection
                await mqtt_manager.initialize()
                logging.info(f"MQTT manager initialized for prefix '{device_prefix}'")
            else:
                mqtt_manager = self.mqtt_managers[device_prefix]
        
        # Process devices
        devices_config = config.get('devices', {})
        for device_name, device_config in devices_config.items():
            await self._process_device(device_name, device_config, mqtt_manager)
    
    async def _process_device(self, device_name: str, device_config: Dict, mqtt_manager: Optional[Any]):
        """Process a single device configuration"""
        if device_name not in self.devices:
            self.devices[device_name] = DeviceProxy(device_name)
        
        device_proxy = self.devices[device_name]
        
        # Process components
        components_config = device_config.get('components', {})
        for component_name, component_config in components_config.items():
            component_type = component_config.get('type')
            
            if not component_type:
                logging.warning(f"No type specified for {device_name}.{component_name}")
                continue
            
            # Create the appropriate component
            if component_type == 'ESPHomeACComponent':
                # Create ESPHome component
                # Remove 'type' from config before passing
                esphome_params = {k: v for k, v in component_config.items() if k != 'type'}
                base_component = ESPHomeComponentAdapter(
                    name=component_name,
                    device_name=device_name,
                    **esphome_params
                )
            else:
                # Create MQTT component
                if not mqtt_manager:
                    logging.error(f"MQTT component {device_name}.{component_name} requires MQTT config")
                    continue
                
                # Make a copy of config to avoid modifying the original
                component_params = component_config.copy()
                
                # Create the raw component using ComponentFactory
                raw_component = ComponentFactory.create_component(
                    component_type,
                    name=component_name,
                    device_name=device_name,
                    **component_params  # ComponentFactory will handle removing 'type'
                )
                
                # Wrap in adapter (don't pass the full config again)
                base_component = MQTTComponentAdapter(
                    wrapped_component=raw_component,
                    name=component_name,
                    device_name=device_name
                )
            
            # Create unified proxy
            unified_proxy = UnifiedComponentProxy(
                device_name=device_name,
                component_name=component_name,
                base_component=base_component
            )
            
            # Add to device
            device_proxy.add_component(component_name, unified_proxy)
            
            # For MQTT components, setup subscription handling
            if mqtt_manager and not isinstance(base_component, ESPHomeComponentAdapter):
                self._setup_mqtt_subscriptions(unified_proxy, mqtt_manager, component_name)
            
            logging.info(f"Created component: {device_name}.{component_name} ({component_type})")
    
    def _setup_mqtt_subscriptions(self, unified_proxy: UnifiedComponentProxy, mqtt_manager: Any, component_name: str):
        """Setup MQTT status subscriptions for a component"""
        base_component = unified_proxy.base_component
        
        # For each status method, setup MQTT subscription
        for status_method in base_component.get_status_methods():
            device_prefix = mqtt_manager.device_prefix
            device_name = unified_proxy.device_name
            
            status_topic = f"{device_prefix}/{device_name}/{component_name}/status/{status_method}"
            
            # Create callback that updates the component
            def make_callback(proxy, component, method):
                async def mqtt_callback(topic, payload):
                    # Emit the status update through the base component
                    component._emit_status_update(method, payload)
                    # Also handle the update in the proxy
                    proxy._handle_status_update(method, payload)
                    logging.info(f"MQTT status received on {topic}: {method} = {payload}")
                return mqtt_callback
            
            callback = make_callback(unified_proxy, base_component, status_method)
            
            # Subscribe through the MQTT manager
            if hasattr(mqtt_manager, '_proxy_subscribe'):
                mqtt_manager._proxy_subscribe(status_topic, callback)
                logging.info(f"Subscribed to MQTT status topic: {status_topic}")
    
    async def _initialize_all_components(self):
        """Initialize all components"""
        # First initialize all MQTT managers
        for device_prefix, mqtt_manager in self.mqtt_managers.items():
            if not mqtt_manager.is_connected:
                logging.info(f"Waiting for MQTT manager '{device_prefix}' to connect...")
                await asyncio.sleep(1)  # Give MQTT time to connect
        
        # Then initialize all components
        init_tasks = []
        
        for device_name, device_proxy in self.devices.items():
            for component_name, unified_proxy in device_proxy.components.items():
                init_tasks.append(self._init_component(device_name, component_name, unified_proxy))
        
        if init_tasks:
            results = await asyncio.gather(*init_tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results if r is True)
            total_count = len(results)
            
            logging.info(f"Component initialization: {success_count}/{total_count} successful")
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logging.error(f"Component initialization failed: {result}")
    
    async def _init_component(self, device_name: str, component_name: str, unified_proxy: UnifiedComponentProxy) -> bool:
        """Initialize a single component"""
        try:
            success = await unified_proxy.initialize()
            if success:
                logging.info(f"Initialized {device_name}.{component_name}")
            else:
                logging.error(f"Failed to initialize {device_name}.{component_name}")
            return success
        except Exception as e:
            logging.error(f"Error initializing {device_name}.{component_name}: {e}")
            return False
    
    def get_device(self, name: str) -> Optional['DeviceProxy']:
        """Get a device by name"""
        return self.devices.get(name)
    
    def list_all_devices(self):
        """List all devices and their components"""
        print("\n=== All Loaded Devices ===")
        for device_name, device_proxy in self.devices.items():
            print(f"\nDevice: {device_name}")
            for comp_name, unified_proxy in device_proxy.components.items():
                component_type = type(unified_proxy.base_component).__name__
                
                # Get available methods
                commands = unified_proxy.base_component.get_command_methods()
                statuses = unified_proxy.base_component.get_status_methods()
                
                print(f"  - {comp_name} ({component_type})")
                if commands:
                    print(f"    Commands: {', '.join(commands)}")
                if statuses:
                    print(f"    Status: {', '.join(statuses)}")
    
    def list_data_commands(self) -> List[Dict[str, Any]]:
        """List all data commands with their associated status methods"""
        commands = []
        
        for device_name, device_proxy in self.devices.items():
            for component_name, unified_proxy in device_proxy.components.items():
                base_component = unified_proxy.base_component
                
                # Get data commands from the component
                data_commands = base_component.get_data_commands()
                
                for cmd_info in data_commands:
                    # Build command info
                    command_str = f"{device_name}.{component_name}.{cmd_info['command']}()"
                    status_str = f"{device_name}.{component_name}.{cmd_info['status']}()"
                    
                    commands.append({
                        "type": type(base_component).__name__,
                        "command_str": command_str,
                        "status_str": status_str,
                        "command_method_name": cmd_info['command'],
                        "command_method": getattr(unified_proxy, cmd_info['command']),
                        "status_method_name": cmd_info['status'],
                        "status_path": f"{device_name}.{component_name}.{cmd_info['status']}",
                        "component_path": f"{device_name}.{component_name}"
                    })
        
        return commands
    
    async def disconnect_all(self):
        """Disconnect all components and MQTT connections"""
        # Disconnect all components
        disconnect_tasks = []
        
        for device_proxy in self.devices.values():
            for unified_proxy in device_proxy.components.values():
                disconnect_tasks.append(unified_proxy.disconnect())
        
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        # Disconnect MQTT managers
        for mqtt_manager in self.mqtt_managers.values():
            await mqtt_manager.disconnect()
        
        logging.info("All connections closed")


class DeviceProxy:
    """Simple device proxy that holds components"""
    
    def __init__(self, device_name: str):
        self.device_name = device_name
        self.components = {}
    
    def add_component(self, component_name: str, unified_proxy: UnifiedComponentProxy):
        """Add a component to this device"""
        self.components[component_name] = unified_proxy
        
        # Also add as attribute for easy access
        setattr(self, component_name, unified_proxy)
    
    def get_component(self, name: str) -> Optional[UnifiedComponentProxy]:
        """Get a component by name"""
        return self.components.get(name)


# Factory function for compatibility
async def create_device_controller(config_directory: str = "configs", component_path: str = "."):
    """Create and initialize the improved config loader"""
    loader = ImprovedConfigLoader(config_directory, component_path)
    await loader.initialize()
    
    # Add devices as attributes to loader for easy access
    for device_name, device_proxy in loader.devices.items():
        setattr(loader, device_name, device_proxy)
    
    return loader


# Test the improved system
if __name__ == "__main__":
    async def test():
        controller = await create_device_controller()
        
        print("\n=== Testing Improved System ===")
        controller.list_all_devices()
        
        # Example usage with MQTT component
        if hasattr(controller, 'hvac'):
            print("\n--- Testing MQTT Component ---")
            # Turn on valve and wait for status
            result = await controller.hvac.avery_valve.execute_and_wait_for_status(
                'on', 'is_on', timeout=5
            )
            print(f"Valve status after ON: {result}")
        
        # Example usage with ESPHome component
        if hasattr(controller, 'living_room_ac'):
            print("\n--- Testing ESPHome Component ---")
            # Set temperature
            await controller.living_room_ac.ac.set_temp(temp=72)
            
            # Get current temperature
            temp_status = await controller.living_room_ac.ac.get_temp_status()
            print(f"AC temperature status: {temp_status}")
        
        # Keep running for a bit to see updates
        await asyncio.sleep(30)
        
        # Cleanup
        await controller.disconnect_all()
    
    asyncio.run(test())