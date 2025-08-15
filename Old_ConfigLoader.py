import yaml
import os
import glob
from ServerDeviceProxy import AsyncServerDeviceManager, ComponentInspector, AsyncComponentProxy
import json
import asyncio
import logging
from ESPHomeACComponent import ESPHomeACComponent

class ESPHomeComponentProxy:
    """Proxy wrapper for ESPHome components to integrate with the existing system"""
    
    def __init__(self, device_name: str, component_name: str, component_config: dict, mqtt_manager, device_prefix: str):
        self.device_name = device_name
        self.component_name = component_name
        self.component_config = component_config
        self.mqtt_manager = mqtt_manager
        self.device_prefix = device_prefix
        self.component_type = component_config.get('type')
        
        # Create the actual ESPHome component
        self.esphome_component = None
        self._initialization_task = None
        
        # Copy all the command and status methods from the ESPHome component
        self._setup_proxy_methods()
    
    def _setup_proxy_methods(self):
        """Setup proxy methods that will delegate to the ESPHome component once initialized"""
        # Get all methods from ESPHomeACComponent that are decorated
        from ESPHomeACComponent import ESPHomeACComponent
        
        for method_name in dir(ESPHomeACComponent):
            method = getattr(ESPHomeACComponent, method_name)
            if callable(method) and (hasattr(method, '_is_mqtt_command') or hasattr(method, '_is_mqtt_status')):
                # Create a proxy method that delegates to the ESPHome component
                self._create_proxy_method(method_name)
    
    def _create_proxy_method(self, method_name: str):
        """Create a proxy method that delegates to the ESPHome component"""
        async def proxy_method(*args, **kwargs):
            if not self.esphome_component:
                raise RuntimeError(f"ESPHome component {self.component_name} not initialized")
            
            actual_method = getattr(self.esphome_component, method_name)
            return await actual_method(*args, **kwargs)
        
        # Copy method attributes for compatibility
        original_method = getattr(ESPHomeACComponent, method_name)
        if hasattr(original_method, '_is_mqtt_command'):
            proxy_method._is_mqtt_command = True
        if hasattr(original_method, '_is_mqtt_status'):
            proxy_method._is_mqtt_status = True
        
        setattr(self, method_name, proxy_method)
    
    async def initialize(self):
        """Initialize the ESPHome component"""
        try:
            # Extract ESPHome-specific config
            esphome_config = {
                'host': self.component_config.get('host'),
                'port': self.component_config.get('port', 6053),
                'password': self.component_config.get('password')
            }
            
            self.esphome_component = ESPHomeACComponent(**esphome_config)
            success = await self.esphome_component.initialize()
            
            if success:
                logging.info(f"ESPHome component {self.device_name}.{self.component_name} initialized successfully")
            else:
                logging.error(f"Failed to initialize ESPHome component {self.device_name}.{self.component_name}")
            
            return success
            
        except Exception as e:
            logging.error(f"Error initializing ESPHome component {self.device_name}.{self.component_name}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect the ESPHome component"""
        if self.esphome_component:
            await self.esphome_component.disconnect()

class AsyncConfigLoader:
    """Async version of ConfigLoader - loads multiple config files and creates device proxies"""
    
    def __init__(self, config_directory: str = "configs", component_path: str = "."):
        self.config_directory = config_directory
        self.device_managers = {}  # One per device_prefix
        self.all_devices = {}  # All devices accessible by name
        self.esphome_components = {}  # Track ESPHome components separately
        self._initialized = False
        
        # Add component path for imports
        ComponentInspector.add_component_path(component_path)
    
    async def initialize(self):
        """Initialize all device managers and ESPHome components"""
        if self._initialized:
            return
        
        await self.load_all_configs()
        
        # Initialize all device managers (for MQTT devices)
        for manager in self.device_managers.values():
            await manager.initialize()
        
        # Initialize all ESPHome components
        await self._initialize_esphome_components()
        
        self._initialized = True
        print("AsyncConfigLoader initialized successfully")
    
    async def _initialize_esphome_components(self):
        """Initialize all ESPHome components"""
        init_tasks = []
        
        for device_name, device_proxy in self.all_devices.items():
            for component_name in dir(device_proxy):
                if not component_name.startswith('_'):
                    component = getattr(device_proxy, component_name)
                    if isinstance(component, ESPHomeComponentProxy):
                        init_tasks.append(component.initialize())
        
        if init_tasks:
            results = await asyncio.gather(*init_tasks, return_exceptions=True)
            
            # Log results
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            logging.info(f"ESPHome component initialization: {success_count}/{total_count} successful")
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logging.error(f"ESPHome component {i} failed to initialize: {result}")
    
    async def load_all_configs(self):
        """Load all YAML config files from the directory"""
        if not os.path.exists(self.config_directory):
            print(f"Config directory '{self.config_directory}' not found")
            return
        
        # Find all .yaml and .yml files
        config_files = glob.glob(os.path.join(self.config_directory, "*.yaml"))
        config_files.extend(glob.glob(os.path.join(self.config_directory, "*.yml")))
        
        print(f"Found {len(config_files)} config files")
        
        for config_file in config_files:
            try:
                await self.load_config_file(config_file)
            except Exception as e:
                print(f"Failed to load config file {config_file}: {e}")
    
    async def load_config_file(self, config_file: str):
        """Load a single config file"""
        print(f"Loading config: {config_file}")
        
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        # Check if this config has any MQTT components or only ESPHome components
        devices_config = config.get('devices', {})
        has_mqtt_components = self._has_mqtt_components(devices_config)
        has_esphome_components = self._has_esphome_components(devices_config)
        
        print(f"Config analysis: MQTT components: {has_mqtt_components}, ESPHome components: {has_esphome_components}")
        
        # Only create MQTT manager if there are MQTT components AND mqtt config exists
        if has_mqtt_components:
            # Extract MQTT config
            mqtt_config = config.get('mqtt', {})
            if not mqtt_config:
                print(f"Warning: Config {config_file} has MQTT components but no MQTT configuration")
                return
            
            device_prefix = mqtt_config.get('device_prefix', 'devices')
            
            # Create or get device manager for this prefix
            if device_prefix not in self.device_managers:
                # Add broker_host if not specified
                if 'broker_host' not in mqtt_config:
                    mqtt_config['broker_host'] = 'localhost'
                
                self.device_managers[device_prefix] = AsyncServerDeviceManager(mqtt_config)
            
            # Load devices into the appropriate manager
            device_manager = self.device_managers[device_prefix]
            
            # Process devices and handle mixed components
            await self._load_mixed_device_config(devices_config, device_manager)
        
        elif has_esphome_components:
            # ESPHome-only config - create a dummy device manager or handle differently
            print(f"Config {config_file} contains only ESPHome components - no MQTT needed")
            await self._load_esphome_only_config(devices_config)
        
        else:
            print(f"Config {config_file} has no recognizable components")
    
    def _has_mqtt_components(self, devices_config: dict) -> bool:
        """Check if any device has MQTT (non-ESPHome) components"""
        for device_config in devices_config.values():
            components = device_config.get('components', {})
            for component_config in components.values():
                component_type = component_config.get('type')
                if component_type and component_type != 'ESPHomeACComponent':
                    return True
        return False
    
    async def _load_esphome_only_config(self, devices_config: dict):
        """Load a config that contains only ESPHome devices"""
        for device_name, device_config in devices_config.items():
            # Create a minimal device proxy for ESPHome-only devices
            esphome_device = self._create_esphome_only_device(device_name, device_config)
            
            if esphome_device:
                self.all_devices[device_name] = esphome_device
                setattr(self, device_name, esphome_device)
                print(f"Created ESPHome-only device: {device_name}")
    
    def _create_esphome_only_device(self, device_name: str, device_config: dict):
        """Create a device proxy that only contains ESPHome components"""
        
        class ESPHomeOnlyDevice:
            def __init__(self, device_name, device_config):
                self.device_name = device_name
                self.device_config = device_config
                self.mqtt_manager = None  # No MQTT for ESPHome-only devices
                self.device_prefix = None
        
        device = ESPHomeOnlyDevice(device_name, device_config)
        
        # Add ESPHome components to this device
        components_config = device_config.get('components', {})
        for component_name, component_config in components_config.items():
            if component_config.get('type') == 'ESPHomeACComponent':
                esphome_proxy = ESPHomeComponentProxy(
                    device_name,
                    component_name,
                    component_config,
                    None,  # No mqtt_manager for ESPHome-only
                    None   # No device_prefix for ESPHome-only
                )
                
                # Add the ESPHome component to the device
                setattr(device, component_name, esphome_proxy)
                
                # Track for initialization
                component_key = f"{device_name}.{component_name}"
                self.esphome_components[component_key] = esphome_proxy
                
                print(f"Added ESPHome component to ESPHome-only device: {device_name}.{component_name}")
        
        return device
    
    async def _load_mixed_device_config(self, devices_config: dict, device_manager):
        """Load devices that may have mixed MQTT and ESPHome components"""
        for device_name, device_config in devices_config.items():
            # Check if this device has ESPHome components
            has_esphome = self._has_esphome_components({device_name: device_config})
            
            if has_esphome:
                # Create device with mixed components (MQTT + ESPHome)
                await self._load_mixed_device(device_name, device_config, device_manager)
            else:
                # Regular MQTT-only device
                device_manager.load_device_config({
                    'devices': {device_name: device_config}
                })
        
        # Add devices to global registry and as attributes
        for device_name, device_proxy in device_manager.devices.items():
            self.all_devices[device_name] = device_proxy
            # Add device as attribute to this loader for easy access
            setattr(self, device_name, device_proxy)
    
    def _has_esphome_components(self, devices_config: dict) -> bool:
        """Check if any device has ESPHome components"""
        for device_config in devices_config.values():
            components = device_config.get('components', {})
            for component_config in components.values():
                if component_config.get('type') == 'ESPHomeACComponent':
                    return True
        return False
    
    async def _load_mixed_device(self, device_name: str, device_config: dict, device_manager):
        """Load a device that has both MQTT and ESPHome components"""
        components_config = device_config.get('components', {})
        
        # Separate MQTT and ESPHome components
        mqtt_components = {}
        esphome_components = {}
        
        for component_name, component_config in components_config.items():
            if component_config.get('type') == 'ESPHomeACComponent':
                esphome_components[component_name] = component_config
            else:
                mqtt_components[component_name] = component_config
        
        # Create device config for MQTT components (if any)
        if mqtt_components:
            mqtt_device_config = device_config.copy()
            mqtt_device_config['components'] = mqtt_components
            
            device_manager.load_device_config({
                'devices': {device_name: mqtt_device_config}
            })
        else:
            # Create empty device if no MQTT components
            device_manager.load_device_config({
                'devices': {device_name: {'components': {}}}
            })
        
        # Get the device proxy that was created
        device_proxy = device_manager.devices[device_name]
        
        # Add ESPHome components to the device proxy
        for component_name, component_config in esphome_components.items():
            esphome_proxy = ESPHomeComponentProxy(
                device_name,
                component_name,
                component_config,
                device_manager,  # mqtt_manager
                device_manager.device_prefix
            )
            
            # Add the ESPHome component to the device proxy
            setattr(device_proxy, component_name, esphome_proxy)
            
            # Track for initialization
            component_key = f"{device_name}.{component_name}"
            self.esphome_components[component_key] = esphome_proxy
            
            print(f"Added ESPHome component: {device_name}.{component_name}")
    
    def get_device(self, name: str):
        """Get any device by name regardless of prefix"""
        return self.all_devices.get(name)
    
    def list_all_devices(self):
        """List all devices from all config files"""
        print("\n=== All Loaded Devices ===")
        for prefix, manager in self.device_managers.items():
            print(f"\nDevice Prefix: {prefix}")
            manager.list_devices()
        
        # Also list ESPHome components
        if self.esphome_components:
            print(f"\n=== ESPHome Components ===")
            for component_key, component in self.esphome_components.items():
                print(f"  {component_key} (ESPHomeACComponent)")
    
    async def disconnect_all(self):
        """Disconnect all MQTT connections and ESPHome components"""
        tasks = []
        
        # Disconnect MQTT managers
        for manager in self.device_managers.values():
            tasks.append(manager.disconnect())
        
        # Disconnect ESPHome components
        for component in self.esphome_components.values():
            tasks.append(component.disconnect())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def list_data_commands(self):
        """
        Generate a list of all available data commands with their proxy methods
        Including ESPHome components
        """
        commands = []
        
        # Process MQTT devices (existing logic)
        for device_name, device_proxy in self.all_devices.items():
            device_config = self._get_device_config(device_name)
            if not device_config:
                continue
                
            components_config = device_config.get('components', {})
            
            for component_name, component_config in components_config.items():
                component_type = component_config.get('type')
                if not component_type or component_type == 'ESPHomeACComponent':
                    continue  # Skip ESPHome components here, handle separately
                    
                # Use ComponentInspector to discover methods
                data_methods = ComponentInspector.discover_data_methods(component_type)
                
                # Add data methods (existing logic)
                for data_method in data_methods:
                    command_method_name = data_method['command_method_name']
                    status_method_name = data_method['status_method_name']

                    # Get signatures from the component class
                    command_signature = self._get_method_signature(component_type, command_method_name)
                    status_signature = self._get_method_signature(component_type, status_method_name)

                    # Build the command/status strings
                    command_str = f"{device_name}.{component_name}.{command_method_name}{command_signature}"
                    status_str = f"{device_name}.{component_name}.{status_method_name}{status_signature}"
                    component_path = f"{device_name}.{component_name}"
                    status_path = f"{device_name}.{component_name}.{status_method_name}"

                    # Get the actual proxy methods from the loaded device
                    try:
                        # Get the component proxy from the device proxy
                        component_proxy = getattr(device_proxy, component_name)
                        
                        # Get the actual proxy methods
                        command_proxy_method = getattr(component_proxy, command_method_name)
                        
                        commands.append({
                            "type": component_type,
                            "command_str": command_str,
                            "status_str": status_str,
                            "command_method_name": command_method_name,
                            "command_method": command_proxy_method,  # Async proxy method
                            "status_method_name": status_method_name,
                            "status_path": status_path,
                            "component_path": component_path
                        })
                        
                    except AttributeError as e:
                        print(f"Warning: Could not get proxy methods for {device_name}.{component_name}: {e}")
                        continue
        
        # Process ESPHome components
        for component_key, esphome_component in self.esphome_components.items():
            device_name, component_name = component_key.split('.', 1)
            
            # Get all command and status methods from ESPHomeACComponent
            from ESPHomeACComponent import ESPHomeACComponent
            
            for method_name in dir(ESPHomeACComponent):
                method = getattr(ESPHomeACComponent, method_name)
                if callable(method) and hasattr(method, '_is_mqtt_command'):
                    # This is a command method
                    command_signature = self._get_esphome_method_signature(method_name)
                    command_str = f"{device_name}.{component_name}.{method_name}{command_signature}"
                    
                    try:
                        command_proxy_method = getattr(esphome_component, method_name)
                        
                        commands.append({
                            "type": "ESPHomeACComponent",
                            "command_str": command_str,
                            "status_str": None,  # ESPHome doesn't use paired command/status
                            "command_method_name": method_name,
                            "command_method": command_proxy_method,
                            "status_method_name": None,
                            "status_path": None,
                            "component_path": f"{device_name}.{component_name}"
                        })
                        
                    except AttributeError as e:
                        print(f"Warning: Could not get ESPHome method {device_name}.{component_name}.{method_name}: {e}")
                        continue
        
        return commands

    def _get_esphome_method_signature(self, method_name: str):
        """Get method signature for ESPHome component methods"""
        try:
            import inspect
            from ESPHomeACComponent import ESPHomeACComponent
            
            method = getattr(ESPHomeACComponent, method_name)
            sig = inspect.signature(method)
            
            params = []
            for name, param in sig.parameters.items():
                if name == 'self':
                    continue
                if param.kind == param.VAR_KEYWORD:
                    continue
                params.append(str(param))
            
            if params:
                return f"({', '.join(params)})"
            else:
                return "()"
                
        except Exception as e:
            return "()"

    def list_all_commands(self, include_status=True):
        """Generate a list of all available commands using ComponentInspector"""
        commands = []
        
        # Process MQTT devices
        for device_name, device_proxy in self.all_devices.items():
            device_config = self._get_device_config(device_name)
            if not device_config:
                continue
                
            components_config = device_config.get('components', {})
            
            for component_name, component_config in components_config.items():
                component_type = component_config.get('type')
                if not component_type or component_type == 'ESPHomeACComponent':
                    continue  # Skip ESPHome, handle separately
                    
                command_methods = ComponentInspector.discover_command_methods(component_type)
                status_methods = ComponentInspector.discover_status_methods(component_type) if include_status else []
                
                for method_name in command_methods:
                    signature = self._get_method_signature(component_type, method_name)
                    command_str = f"await {device_name}.{component_name}.{method_name}{signature}"
                    commands.append(command_str)
                
                for method_name in status_methods:
                    signature = self._get_method_signature(component_type, method_name)
                    command_str = f"await {device_name}.{component_name}.{method_name}{signature}"
                    commands.append(command_str)
        
        # Process ESPHome components
        from ESPHomeACComponent import ESPHomeACComponent
        for component_key, esphome_component in self.esphome_components.items():
            device_name, component_name = component_key.split('.', 1)
            
            for method_name in dir(ESPHomeACComponent):
                method = getattr(ESPHomeACComponent, method_name)
                if callable(method) and (hasattr(method, '_is_mqtt_command') or 
                                       (include_status and hasattr(method, '_is_mqtt_status'))):
                    signature = self._get_esphome_method_signature(method_name)
                    command_str = f"await {device_name}.{component_name}.{method_name}{signature}"
                    commands.append(command_str)
        
        return sorted(commands)

    def _get_device_config(self, device_name: str):
        """Get the original config for a device"""
        for manager in self.device_managers.values():
            if hasattr(manager, 'devices') and device_name in manager.devices:
                device_proxy = manager.devices[device_name]
                if hasattr(device_proxy, 'device_config'):
                    return device_proxy.device_config
        return None

    def _get_method_signature(self, component_type: str, method_name: str):
        """Get the actual method signature by inspecting the component class"""
        try:
            import importlib
            import inspect
            
            module = importlib.import_module(component_type)
            component_class = getattr(module, component_type)
            method = getattr(component_class, method_name)
            
            sig = inspect.signature(method)
            
            params = []
            for name, param in sig.parameters.items():
                if name == 'self':
                    continue
                if param.kind == param.VAR_KEYWORD:
                    continue
                params.append(str(param))
            
            if params:
                return f"({', '.join(params)})"
            else:
                return "()"
                
        except Exception as e:
            return "()"

    def print_all_commands(self, include_status=True):
        """Print all available commands to the terminal"""
        commands = self.list_all_commands(include_status)
        
        print(f"\nAvailable Commands ({len(commands)} total):")
        print("=" * 50)
        print("Note: All commands are now async and must be awaited!")
        print("=" * 50)
        
        by_device = {}
        for cmd in commands:
            device = cmd.split('.')[0].replace('await ', '')  # Remove await for grouping
            if device not in by_device:
                by_device[device] = []
            by_device[device].append(cmd)
            
        for device, cmds in by_device.items():
            print(f"\n{device.upper()}:")
            for cmd in cmds:
                if self._is_status_method(cmd):
                    print(f"  {cmd} [STATUS]")
                elif self._is_esphome_method(cmd):
                    print(f"  {cmd} [ESPHOME]")
                else:
                    print(f"  {cmd}")

    def _is_status_method(self, command_str: str):
        """Check if a command string represents a status method"""
        try:
            # Remove 'await ' prefix for parsing
            clean_cmd = command_str.replace('await ', '')
            parts = clean_cmd.split('.')
            if len(parts) < 3:
                return False
                
            device_name = parts[0]
            component_name = parts[1]
            method_name = parts[2].split('(')[0]
            
            # Check if this is an ESPHome component first
            component_key = f"{device_name}.{component_name}"
            if component_key in self.esphome_components:
                from ESPHomeACComponent import ESPHomeACComponent
                method = getattr(ESPHomeACComponent, method_name, None)
                return method and hasattr(method, '_is_mqtt_status')
            
            # Regular MQTT component
            device_config = self._get_device_config(device_name)
            if not device_config:
                return False
                
            component_config = device_config.get('components', {}).get(component_name, {})
            component_type = component_config.get('type')
            
            if not component_type:
                return False
                
            status_methods = ComponentInspector.discover_status_methods(component_type)
            return method_name in status_methods
            
        except Exception:
            return False

    def _is_esphome_method(self, command_str: str):
        """Check if a command string represents an ESPHome method"""
        try:
            clean_cmd = command_str.replace('await ', '')
            parts = clean_cmd.split('.')
            if len(parts) < 3:
                return False
                
            device_name = parts[0]
            component_name = parts[1]
            component_key = f"{device_name}.{component_name}"
            
            return component_key in self.esphome_components
            
        except Exception:
            return False

    def get_commands_json(self, include_status=True):
        """Get all commands as JSON string for API endpoints"""
        import json
        return json.dumps(self.get_commands(include_status), indent=2)

    def get_commands(self, include_status=True):
        commands = self.list_all_commands(include_status)
        
        command_list = []
        status_list = []
        esphome_list = []
        
        for cmd in commands:
            if self._is_esphome_method(cmd):
                esphome_list.append(cmd)
            elif self._is_status_method(cmd):
                status_list.append(cmd)
            else:
                command_list.append(cmd)

        return {
            "commands": command_list,
            "status_methods": status_list,
            "esphome_methods": esphome_list,
            "total": len(commands)
        }

# Updated factory function
async def create_device_controller(config_directory: str = "configs", component_path: str = "."):
    """Create and return a configured async device controller"""
    loader = AsyncConfigLoader(config_directory, component_path)
    await loader.initialize()
    return loader

# Convenience function for testing
async def test_controller():
    """Test function to create controller and show usage"""
    controller = await create_device_controller()
    
    print("\n=== Testing Controller ===")
    controller.print_all_commands()
    
    # Example usage:
    try:
        # MQTT device example (if exists):
        # result = await controller.hvac.avery_valve.on()
        # print(f"Command result: {result}")
        
        # ESPHome AC example (if exists):
        # await controller.living_room_ac.set_temp(temp=72)
        # current_temp = await controller.living_room_ac.get_current_temp()
        # print(f"Current temperature: {current_temp}")
        
        pass
    except AttributeError as e:
        print(f"Device/component not found: {e}")
    except Exception as e:
        print(f"Error executing command: {e}")
    
    return controller

# Test in async context
if __name__ == "__main__":
    async def main():
        controller = await test_controller()
        
        # Keep alive for testing
        print("\nController ready for testing.")
        print("MQTT devices: Use 'await controller.device.component.method()' syntax")
        print("ESPHome ACs: Use 'await controller.ac_name.set_temp(temp=72)' syntax")
        
        # Example interactive session:
        # await controller.hvac.avery_valve.on()
        # await controller.hvac.temp_sensor.get_temperature()
        # await controller.living_room_ac.set_temp(temp=72)
        # await controller.living_room_ac.get_current_temp()
        
    asyncio.run(main())