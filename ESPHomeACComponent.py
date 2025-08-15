# ESPHomeACComponent.py
import asyncio
import logging
import time
from aioesphomeapi import APIClient, APIConnectionError, ClimatePreset, ClimateFanMode, ClimateSwingMode, ClimateMode
from typing import Optional, Dict, Any
from Component import Component, command, status

from GlobalRegistry import GlobalRegistry

class ESPHomeACComponent(Component):
    """ESPHome AC component that integrates with your AsyncConfigLoader system"""
    
    def __init__(self, **config):
        """
        Initialize ESPHome AC component from YAML config
        
        Expected config parameters:
        - host: IP address of ESPHome device
        - port: API port (default 6053)
        - password: API password (optional)
        """
        # Extract name and device_name for Component base class
        name = config.get('name')
        device_name = config.get('device_name')
        
        # Initialize parent Component class (but skip MQTT setup since we don't need it)
        super().__init__(name=name, device_name=device_name)
        
        self.host = config.get('host')
        self.port = config.get('port', 6053)
        self.password = config.get('password')
        
        if not self.host:
            raise ValueError("ESPHome AC component requires 'host' parameter")
        
        # ESPHome API client
        self.client = APIClient(self.host, self.port, self.password)
        self.connected = False
        
        # Entity references (discovered during connection)
        self.climate_entities = []
        self.sensor_entities = []
        self.switch_entities = []
        self.select_entities = []
        self.number_entities = []
        
        # State tracking
        self.climate_state = {}
        self.sensor_states = {}
        
        # Last known state for status methods
        self.last_current_temp = None
        self.last_target_temp = None
        self.last_mode = None
        self.last_fan_mode = None
        self.last_preset = None
        self.last_power_consumption = None
        self.last_heartbeat = None
        
        self._pending_commands = {}  # Dict[str, Any] - tracks expected state changes
        self._command_timeout = 2.0

        # Connection task
        self._connection_task = None
        self._state_subscription_task = None
        self._reconnection_lock = asyncio.Lock()  # Prevent multiple concurrent reconnections
        
        logging.info(f"ESPHome AC component initialized for {self.host}:{self.port}")
    
    def get_temp_limits(self) -> tuple:
        """Get the actual temperature limits from the device"""
        if not self.climate_entities:
            logging.warning(f"No climate entities found for {self.host}, using default limits")
            return (17.0, 30.0)  # Fallback
        
        climate_entity = self.climate_entities[0]
        
        # Get min/max temperature from the climate entity
        min_temp = getattr(climate_entity, 'min_temperature', 17.0)
        max_temp = getattr(climate_entity, 'max_temperature', 30.0)
        
        logging.info(f"Device {self.host} temperature limits: {min_temp}°C to {max_temp}°C")
        return (min_temp, max_temp)
    
    def clamp_temperature(self, temp: float) -> float:
        """Clamp temperature to device limits"""
        min_temp, max_temp = self.get_temp_limits()
        
        if temp < min_temp:
            logging.info(f"Temperature {temp}°C clamped to minimum {min_temp}°C")
            return min_temp
        elif temp > max_temp:
            logging.info(f"Temperature {temp}°C clamped to maximum {max_temp}°C")
            return max_temp
        
        return temp

    def _setup_mqtt(self):
        """Override parent's MQTT setup since ESPHome doesn't use MQTT"""
        # ESPHome components don't use MQTT - they use the native API
        # So we skip the parent's MQTT setup
        pass

    def _track_command(self, command_type: str, expected_value: Any):
        """Track a command that we expect to see reflected in state"""
        self._pending_commands[command_type] = {
            'expected_value': expected_value,
            'timestamp': time.time(),
            'refreshed': False
        }
        logging.debug(f"Tracking command: {command_type} = {expected_value}")
    
    def _check_pending_commands(self):
        """Check if any pending commands have been reflected in state"""
        current_time = time.time()
        completed_commands = []
        
        for command_type, command_info in self._pending_commands.items():
            # Check if command timed out
            if current_time - command_info['timestamp'] > self._command_timeout:
                completed_commands.append(command_type)
                logging.warning(f"Command timeout for {command_type}")
                continue
            
            # Check if expected state change occurred
            current_value = None
            if command_type == 'target_temp':
                current_value = self.last_target_temp
            elif command_type == 'mode':
                current_value = self.last_mode
            elif command_type == 'fan_mode':
                current_value = self.last_fan_mode
            elif command_type == 'preset':
                current_value = self.last_preset
            
            if current_value == command_info['expected_value']:
                completed_commands.append(command_type)
                logging.debug(f"Command completed: {command_type} = {current_value}")
            elif not command_info['refreshed']:
                # Trigger a refresh if we haven't already
                asyncio.create_task(self._trigger_single_refresh())
                command_info['refreshed'] = True
        
        # Remove completed commands
        for command_type in completed_commands:
            del self._pending_commands[command_type]

    async def _trigger_single_refresh(self):
        """Trigger a single state refresh"""
        if not GlobalRegistry.is_available():
            return
        
        await asyncio.sleep(0.2)  # 200ms delay
        
        status_paths = [
            f"{self.device_name}.{self.name}.temp_status",
            f"{self.device_name}.{self.name}.target_temp_status",
            f"{self.device_name}.{self.name}.mode_status",
            f"{self.device_name}.{self.name}.fan_mode_status", 
            f"{self.device_name}.{self.name}.preset_status"
        ]
        
        for path in status_paths:
            GlobalRegistry.trigger_state_refresh(path)
        
        logging.debug(f"Triggered single refresh for {self.host}")
    
    async def initialize(self):
        """Initialize connection to ESPHome device"""
        try:
            # Ensure client is properly created
            if not self.client:
                logging.error(f"ESPHome client not created for {self.host}")
                return False
            
            await self.client.connect(login=True)
            self.connected = True
            
            # Get device info
            device_info = await self.client.device_info()
            logging.info(f"Connected to ESPHome device: {device_info.name} (v{device_info.esphome_version})")
            
            # Discover entities
            await self._discover_entities()
            
            # Start state subscription immediately (not as a task)
            await self._setup_state_subscription()
            
            return True
            
        except APIConnectionError as e:
            logging.error(f"Failed to connect to ESPHome device {self.host}: {e}")
            self.connected = False
            return False
        except Exception as e:
            logging.error(f"Unexpected error initializing ESPHome device {self.host}: {e}")
            self.connected = False
            return False
    
    async def _reconnect(self):
        """Attempt to reconnect to the ESPHome device"""
        async with self._reconnection_lock:
            if self.connected:
                # Another task already reconnected
                return True
            
            logging.info(f"Attempting to reconnect to ESPHome device {self.host}")
            
            try:
                # Clean up old client
                if self.client:
                    try:
                        await self.client.disconnect()
                    except:
                        pass  # Ignore errors during cleanup
                
                # Create new client
                self.client = APIClient(self.host, self.port, self.password)
                
                # Connect with login
                await self.client.connect(login=True)
                self.connected = True
                
                # Get device info to verify connection
                device_info = await self.client.device_info()
                logging.info(f"Reconnected to ESPHome device: {device_info.name} (v{device_info.esphome_version})")
                
                # Re-discover entities (they might have changed)
                await self._discover_entities()
                
                # Re-establish state subscription
                await self._setup_state_subscription()
                
                logging.info(f"Successfully reconnected to ESPHome device {self.host}")
                return True
                
            except APIConnectionError as e:
                logging.error(f"Failed to reconnect to ESPHome device {self.host}: {e}")
                self.connected = False
                return False
            except Exception as e:
                logging.error(f"Unexpected error reconnecting to ESPHome device {self.host}: {e}")
                self.connected = False
                return False
    
    async def _discover_entities(self):
        """Discover all entities on the ESPHome device - enhanced with temp limit logging"""
        entities, services = await self.client.list_entities_services()
        
        self.climate_entities = []
        self.sensor_entities = []
        self.switch_entities = []
        self.select_entities = []
        self.number_entities = []
        
        logging.info(f"Discovering entities for ESPHome device {self.host}")
        
        for entity in entities:
            entity_type = type(entity).__name__
            
            if entity_type == 'ClimateInfo':
                self.climate_entities.append(entity)
                logging.info(f"  Found climate entity: {entity.object_id}")
                
                # Log temperature limits
                min_temp = getattr(entity, 'min_temperature', None)
                max_temp = getattr(entity, 'max_temperature', None)
                temp_step = getattr(entity, 'temperature_step', None)
                
                if min_temp is not None and max_temp is not None:
                    logging.info(f"    Temperature range: {min_temp}°C to {max_temp}°C")
                    if temp_step is not None:
                        logging.info(f"    Temperature step: {temp_step}°C")
                else:
                    logging.warning(f"    Temperature limits not available, using defaults")
                
                # Log visual limits (for UI display)
                visual_min = getattr(entity, 'visual_min_temperature', None)
                visual_max = getattr(entity, 'visual_max_temperature', None)
                if visual_min is not None and visual_max is not None:
                    logging.info(f"    Visual temperature range: {visual_min}°C to {visual_max}°C")
                
                # Log supported features (existing code)
                if hasattr(entity, 'supported_presets'):
                    logging.info(f"    Supported presets: {entity.supported_presets}")
                if hasattr(entity, 'supported_custom_presets'):
                    logging.info(f"    Supported custom presets: {entity.supported_custom_presets}")
                if hasattr(entity, 'supported_modes'):
                    logging.info(f"    Supported modes: {entity.supported_modes}")
                if hasattr(entity, 'supported_fan_modes'):
                    logging.info(f"    Supported fan modes: {entity.supported_fan_modes}")
                if hasattr(entity, 'supported_custom_fan_modes'):
                    logging.info(f"    Supported custom fan modes: {entity.supported_custom_fan_modes}")
                if hasattr(entity, 'supported_swing_modes'):
                    logging.info(f"    Supported swing modes: {entity.supported_swing_modes}")
                    
            elif entity_type == 'SensorInfo':
                self.sensor_entities.append(entity)
                if 'power' in entity.object_id.lower():
                    logging.info(f"  Found power sensor: {entity.object_id}")
                elif 'temperature' in entity.object_id.lower():
                    logging.info(f"  Found temperature sensor: {entity.object_id}")
            elif entity_type == 'SwitchInfo':
                self.switch_entities.append(entity)
                if 'boost' in entity.object_id.lower():
                    logging.info(f"  Found boost switch: {entity.object_id}")
            elif entity_type == 'SelectInfo':
                self.select_entities.append(entity)
                if 'boost' in entity.object_id.lower():
                    logging.info(f"  Found boost select: {entity.object_id}")
            elif entity_type == 'NumberInfo':
                self.number_entities.append(entity)
        
        logging.info(f"Entity discovery complete: {len(self.climate_entities)} climate, "
                    f"{len(self.sensor_entities)} sensors, {len(self.switch_entities)} switches, "
                    f"{len(self.select_entities)} selects, {len(self.number_entities)} numbers")
    
    async def _setup_state_subscription(self):
        """Subscribe to state changes from ESPHome device"""
        # Multiple checks to ensure client is ready
        if not self.client:
            logging.error(f"Cannot setup state subscription for {self.host}: client is None")
            return
            
        if not self.connected:
            logging.error(f"Cannot setup state subscription for {self.host}: not connected")
            return
        
        # Test if client is still functional
        try:
            # Try to call a simple method to verify connection is still active
            await self.client.device_info()
        except Exception as e:
            logging.error(f"ESPHome client connection test failed for {self.host}: {e}")
            self.connected = False
            return
        
        def on_state_change(state):
            """Handle state changes from ESPHome device"""
            try:
                entity_key = state.key
                
                # Update internal state tracking
                if hasattr(state, 'current_temperature'):
                    # Climate entity
                    old_climate_state = self.climate_state.get(entity_key, {})
                    new_climate_state = {
                        'current_temperature': getattr(state, 'current_temperature', None),
                        'target_temperature': getattr(state, 'target_temperature', None),
                        'mode': getattr(state, 'mode', None),
                        'action': getattr(state, 'action', None),
                        'fan_mode': getattr(state, 'fan_mode', None),
                        'preset': getattr(state, 'preset', None),
                    }

                    self.climate_state[entity_key] = new_climate_state
                    
                    # Check what changed and trigger appropriate events
                    self._check_climate_changes(old_climate_state, new_climate_state)
                    
                else:
                    # Sensor or other entity
                    old_value = self.sensor_states.get(entity_key)
                    new_value = getattr(state, 'state', None)
                    self.sensor_states[entity_key] = new_value
                    
                    # Check for power sensor changes
                    self._check_sensor_changes(entity_key, old_value, new_value)
                    
            except Exception as e:
                logging.error(f"Error processing state change for {self.host}: {e}")
        
        try:
            # Subscribe to state changes (this is NOT async)
            # Note: Each call to subscribe_states replaces the previous subscription
            # So we don't need to worry about multiple subscriptions
            self.client.subscribe_states(on_state_change)
            logging.info(f"State subscription active for ESPHome device {self.host}")
        except Exception as e:
            logging.error(f"Failed to subscribe to states for {self.host}: {e}")
            # Don't mark as disconnected unless it's a connection error
            if "connection" in str(e).lower() or "disconnect" in str(e).lower():
                self.connected = False
    
    def _check_climate_changes(self, old_state: dict, new_state: dict):
        """Check for climate changes and trigger appropriate events"""
        # Current temperature changed
        if old_state.get('current_temperature') != new_state.get('current_temperature'):
            self.last_current_temp = new_state.get('current_temperature')
            self.trigger_event('temp_status')
            self.auto_publish_on_event('temp_status')
        
        # Target temperature changed
        if old_state.get('target_temperature') != new_state.get('target_temperature'):
            self.last_target_temp = new_state.get('target_temperature')
            self.trigger_event('target_temp_status')
            self.auto_publish_on_event('target_temp_status')
        
        # Mode changed
        if old_state.get('mode') != new_state.get('mode'):
            mode_value = new_state.get('mode')

            try:
                if isinstance(mode_value, ClimateMode):
                    # Convert enum to string (e.g., ClimateFanMode.LOW → 'low')
                    self.last_mode = mode_value.name.lower()
                elif isinstance(mode_value, str):
                    # Already a string, standardize format
                    self.last_mode = mode_value.lower()
                elif mode_value == None:
                    self.last_mode = "None" 
                else:
                    # Unexpected type (e.g., int or something else), fallback
                    self.last_mode = str(mode_value)
            except Exception as e:
                # Log and use a safe fallback
                logging.warning(f"Unknown mode: {mode_value} ({type(mode_value)}): {e}")
                self.last_mode = "unknown"
        
        # Fan mode changed
        if old_state.get('fan_mode') != new_state.get('fan_mode'):
            fan_mode_value = new_state.get('fan_mode')

            try:
                if isinstance(fan_mode_value, ClimateFanMode):
                    # Convert enum to string (e.g., ClimateFanMode.LOW → 'low')
                    self.last_fan_mode = fan_mode_value.name.lower()
                elif isinstance(fan_mode_value, str):
                    # Already a string, standardize format
                    self.last_fan_mode = fan_mode_value.lower()
                elif fan_mode_value == None:
                    self.last_fan_mode = "None"  
                else:
                    # Unexpected type (e.g., int or something else), fallback
                    self.last_fan_mode = str(fan_mode_value)
            except Exception as e:
                # Log and use a safe fallback
                logging.warning(f"Unknown fan mode: {fan_mode_value} ({type(fan_mode_value)}): {e}")
                self.last_fan_mode = "unknown"
        
        self.trigger_event('fan_mode_status')
        self.auto_publish_on_event('fan_mode_status')
    
        # Preset mode changed
        if old_state.get('preset') != new_state.get('preset'):
            preset_mode_value = new_state.get('preset')
            print('PRESET MODE VALUE')
            print(preset_mode_value)
            try:
                if isinstance(preset_mode_value, ClimatePreset):
                    # Convert enum to string (e.g., ClimateFanMode.LOW → 'low')
                    self.last_preset = preset_mode_value.name.lower()
                elif isinstance(preset_mode_value, str):
                    # Already a string, standardize format
                    self.last_preset = preset_mode_value.lower()
                elif preset_mode_value == None:
                    self.last_preset = "None"    
                else:
                    # Unexpected type (e.g., int or something else), fallback
                    self.last_preset = str(preset_mode_value)
            except Exception as e:
                # Log and use a safe fallback
                logging.warning(f"Unknown preset mode: {preset_mode_value} ({type(preset_mode_value)}): {e}")
                self.last_preset = "unknown"
            
        self.trigger_event('preset_status')
        self.auto_publish_on_event('preset_status')
    
    def _check_sensor_changes(self, entity_key: str, old_value: Any, new_value: Any):
        """Check for sensor changes and trigger appropriate events"""
        # Check for power sensor changes
        power_sensors = [s for s in self.sensor_entities 
                        if 'power' in s.object_id.lower() or 'watt' in s.object_id.lower()]
        
        for sensor in power_sensors:
            if sensor.key == entity_key and old_value != new_value:
                self.last_power_consumption = new_value
                self.trigger_event('power_status')
                self.auto_publish_on_event('power_status')
                break
    
    async def _ensure_connected(self):
        """Ensure we have a valid connection, reconnect if needed"""
        if not self.connected:
            success = await self._reconnect()
            if not success:
                raise RuntimeError(f"ESPHome device {self.host} not connected and reconnection failed")
    
    # Command methods (using your existing @command decorator)
    
    @command(data_command=True, events=['temp_status', 'target_temp_status', 'mode_status', 'fan_mode_status', 'preset_status'])
    async def read_status(self):
        """Read AC status - triggers auto-publish of all status events"""
        # This doesn't actually need to do anything since state subscription handles updates
        # But we trigger the events to ensure status is published
        self.trigger_event('temp_status')
        self.trigger_event('target_temp_status') 
        self.trigger_event('mode_status')
        self.trigger_event('fan_mode_status')
        self.trigger_event('preset_status')
        
        self.auto_publish_on_event('temp_status')
        self.auto_publish_on_event('target_temp_status')
        self.auto_publish_on_event('mode_status')
        self.auto_publish_on_event('fan_mode_status')
        self.auto_publish_on_event('preset_status')
    
    @command()
    async def set_temp(self, temp: float):
        """Set target temperature"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            raise RuntimeError(f"ESPHome device {self.host} has no climate entity")

        clamped_temp = self.clamp_temperature(temp)

        self._track_command('target_temp', clamped_temp)

        climate_key = self.climate_entities[0].key
        self.client.climate_command(  # Remove await here
            key=climate_key,
            target_temperature=float(clamped_temp)
        )
        logging.info(f"Set temperature to {clamped_temp}°C on {self.host}")

    @command()
    async def set_mode(self, mode: str):
        """Set AC mode (heat, cool, auto, off, etc.)"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            raise RuntimeError(f"ESPHome device {self.host} has no climate entity")
        
        try:
            mode_value = getattr(ClimateMode, mode.upper(), "OFF")
        except ValueError:
            logging.warning(f"{mode.upper()} not found in available ClimateMode.")

        self._track_command('mode', mode.lower())

        climate_key = self.climate_entities[0].key
        self.client.climate_command(  # Remove await here
            key=climate_key,
            mode=mode_value
        )
        logging.info(f"Set mode to {mode} on {self.host}")

        self.trigger_event('mode_status')
        self.auto_publish_on_event('mode_status')

        asyncio.create_task(self._trigger_immediate_refresh_delayed())

    @command()
    async def set_fan_mode(self, fan_mode: str):
        """Set fan mode (auto, low, medium, high, etc.)"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            raise RuntimeError(f"ESPHome device {self.host} has no climate entity")
        
        try:
            fan_mode_value = getattr(ClimateFanMode, fan_mode.upper(), "AUTO")
        except ValueError:
            logging.warning(f"{fan_mode.upper()} not found in available ClimateFanMode.")

        self._track_command('fan_mode', fan_mode.lower())

        climate_key = self.climate_entities[0].key
        self.client.climate_command(  # Remove await here
            key=climate_key,
            fan_mode=fan_mode_value
        )
        logging.info(f"Set fan mode to {fan_mode} on {self.host}")

        self.trigger_event('fan_status')
        self.auto_publish_on_event('fan_status')

        asyncio.create_task(self._trigger_immediate_refresh_delayed())

    @command()
    async def set_preset(self, preset: str):
        """Set preset mode (boost, sleep, eco, none, etc.)"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            raise RuntimeError(f"ESPHome device {self.host} has no climate entity")
        
        climate_key = self.climate_entities[0].key
        
        # Use the mapped value if available, otherwise try the value as-is
        try:
            preset_value = getattr(ClimatePreset, preset.upper(), "NONE")
        except ValueError:
            logging.warning(f"{preset.upper()} not found in available ClimatePresets.")
        
        self._track_command('preset', preset.lower())

        # Check if it's a standard preset
        climate_entity = self.climate_entities[0]
        supported_presets = getattr(climate_entity, 'supported_presets', [])
        supported_custom_presets = getattr(climate_entity, 'supported_custom_presets', [])
        logging.debug(f"Found available presets: {supported_presets}. Checking for: {preset_value}")
        if preset_value in supported_presets:
            self.client.climate_command(  # Remove await here
                key=climate_key,
                preset=preset_value
            )
            logging.info(f"Set preset to {preset_value} on {self.host}")
        elif preset in supported_custom_presets:
            # Custom presets use a different parameter
            self.client.climate_command(  # Remove await here
                key=climate_key,
                custom_preset=preset_value
            )
            logging.info(f"Set custom preset to {preset} on {self.host}")
        else:
            available = [p for p in supported_presets] + supported_custom_presets
            raise ValueError(f"Preset '{preset}' not supported. Available: {available}")

        self.trigger_event('preset_status')
        self.auto_publish_on_event('preset_status')

        asyncio.create_task(self._trigger_immediate_refresh_delayed())

    @command()
    async def set_boost_mode(self, enabled: bool):
        """Enable/disable boost mode via switch"""
        await self._ensure_connected()
        
        boost_switches = [s for s in self.switch_entities if 'boost' in s.object_id.lower()]
        
        if boost_switches:
            switch_key = boost_switches[0].key
            self.client.switch_command(key=switch_key, state=enabled)  # Remove await here
            logging.info(f"Boost mode {'enabled' if enabled else 'disabled'} on {self.host}")
        else:
            # Try to use preset instead
            if enabled:
                await self.set_preset('boost')
            else:
                await self.set_preset('none')

    @command()
    async def set_boost_mode_select(self, mode: str):
        """Set boost mode via select entity"""
        await self._ensure_connected()
        
        boost_selects = [s for s in self.select_entities if 'boost' in s.object_id.lower()]
        
        if boost_selects:
            select_entity = boost_selects[0]
            if hasattr(select_entity, 'options') and mode in select_entity.options:
                self.client.select_command(key=select_entity.key, state=mode)  # Remove await here
                logging.info(f"Boost mode set to {mode} on {self.host}")
            else:
                available_modes = getattr(select_entity, 'options', [])
                raise ValueError(f"Invalid boost mode '{mode}'. Available: {available_modes}")
        else:
            raise RuntimeError(f"No boost select found on ESPHome device {self.host}")
    
    @command()
    async def get_available_presets(self):
        """Get list of available presets for this AC"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            return []
        
        climate_entity = self.climate_entities[0]
        presets = []
        
        # Standard presets - these come as string constants from ESPHome
        if hasattr(climate_entity, 'supported_presets'):
            # Map ESPHome constants to friendly names
            preset_map = {
                '0': 'none',
                '3': 'boost',
                '5': 'eco',
                '6': 'sleep',
            }
            for preset_const in climate_entity.supported_presets:
                friendly_name = preset_map.get(preset_const, preset_const.lower())
                presets.append(friendly_name)
        
        # Custom presets - these are already strings
        if hasattr(climate_entity, 'supported_custom_presets'):
            presets.extend(climate_entity.supported_custom_presets)
        
        logging.info(f"Available presets for {self.host}: {presets}")
        return presets
    
    @command()
    async def turn_on(self):
        """Turn AC on (set to cool mode)"""
        await self.set_mode("cool")
    
    @command()
    async def turn_off(self):
        """Turn AC off"""
        await self.set_mode("off")
    
    @command(data_command=True, events=['heartbeat_status'])
    async def heartbeat(self):
        """Heartbeat command - ping the ESPHome device"""
        try:
            if not self.connected:
                # Try to reconnect first
                logging.info(f"Heartbeat: Device {self.host} not connected, attempting reconnection")
                success = await self._reconnect()
                if not success:
                    heartbeat_data = {
                        "status": "offline",
                        "timestamp": time.time(),
                        "host": self.host,
                        "error": "Not connected and reconnection failed"
                    }
                    self.last_heartbeat = heartbeat_data
                    self.trigger_event('heartbeat_status')
                    self.auto_publish_on_event('heartbeat_status')
                    return
            
            # Try to get device info as a heartbeat
            device_info = await self.client.device_info()
            heartbeat_data = {
                "status": "online",
                "timestamp": time.time(),
                "host": self.host,
                "device_name": device_info.name,
                "esphome_version": device_info.esphome_version,
                "mac_address": device_info.mac_address
            }
            
            self.last_heartbeat = heartbeat_data
            self.trigger_event('heartbeat_status')
            self.auto_publish_on_event('heartbeat_status')
            
        except Exception as e:
            logging.error(f"Heartbeat failed for {self.host}: {e}")
            
            # Mark as disconnected and try to reconnect
            self.connected = False
            
            logging.info(f"Heartbeat: Connection lost to {self.host}, attempting reconnection")
            success = await self._reconnect()
            
            if success:
                # Retry the heartbeat after successful reconnection
                try:
                    device_info = await self.client.device_info()
                    heartbeat_data = {
                        "status": "online",
                        "timestamp": time.time(),
                        "host": self.host,
                        "device_name": device_info.name,
                        "esphome_version": device_info.esphome_version,
                        "mac_address": device_info.mac_address,
                        "reconnected": True
                    }
                    logging.info(f"Heartbeat: Successfully reconnected to {self.host}")
                except Exception as retry_e:
                    logging.error(f"Heartbeat: Reconnection succeeded but device_info failed: {retry_e}")
                    heartbeat_data = {
                        "status": "error",
                        "timestamp": time.time(),
                        "host": self.host,
                        "error": f"Reconnected but device_info failed: {str(retry_e)}"
                    }
            else:
                heartbeat_data = {
                    "status": "error",
                    "timestamp": time.time(),
                    "host": self.host,
                    "error": f"Connection failed and reconnection failed: {str(e)}"
                }
            
            self.last_heartbeat = heartbeat_data
            self.trigger_event('heartbeat_status')
            self.auto_publish_on_event('heartbeat_status')
    
    @command()
    async def get_device_info(self):
        """Get comprehensive device information including temperature limits"""
        await self._ensure_connected()
        
        if not self.climate_entities:
            return {"error": "No climate entities found"}
        
        climate_entity = self.climate_entities[0]
        
        # Collect all available device info
        device_info = {
            "host": self.host,
            "entity_id": climate_entity.object_id,
            "temperature_limits": {
                "min": getattr(climate_entity, 'min_temperature', None),
                "max": getattr(climate_entity, 'max_temperature', None),
                "step": getattr(climate_entity, 'temperature_step', None)
            },
            "supported_features": {
                "modes": getattr(climate_entity, 'supported_modes', []),
                "fan_modes": getattr(climate_entity, 'supported_fan_modes', []),
                "custom_fan_modes": getattr(climate_entity, 'supported_custom_fan_modes', []),
                "presets": getattr(climate_entity, 'supported_presets', []),
                "custom_presets": getattr(climate_entity, 'supported_custom_presets', []),
                "swing_modes": getattr(climate_entity, 'supported_swing_modes', [])
            },
            "capabilities": {
                "supports_current_temperature": hasattr(climate_entity, 'supports_current_temperature'),
                "supports_two_point_target_temperature": getattr(climate_entity, 'supports_two_point_target_temperature', False),
                "visual_min_temperature": getattr(climate_entity, 'visual_min_temperature', None),
                "visual_max_temperature": getattr(climate_entity, 'visual_max_temperature', None),
                "visual_temperature_step": getattr(climate_entity, 'visual_temperature_step', None)
            }
        }
        
        logging.info(f"Device info for {self.host}: {device_info}")
        return device_info

    # Status methods (using your existing @status decorator)
    
    @status(auto_publish=True, trigger_on=['temp_status'])
    def temp_status(self):
        """Get current temperature reading - auto-published when temp_status event occurs"""
        return {
            "event": "temp_status",
            "timestamp": time.time(),
            "current_temperature": self.last_current_temp,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['target_temp_status'])
    def target_temp_status(self):
        """Get target temperature setting - auto-published when target_temp_status event occurs"""
        return {
            "event": "target_temp_status", 
            "timestamp": time.time(),
            "target_temperature": self.last_target_temp,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['mode_status'])
    def mode_status(self):
        """Get current AC mode - auto-published when mode_status event occurs"""
        return {
            "event": "mode_status",
            "timestamp": time.time(),
            "mode": self.last_mode,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['fan_mode_status'])
    def fan_mode_status(self):
        """Get current fan mode - auto-published when fan_mode_status event occurs"""
        return {
            "event": "fan_mode_status",
            "timestamp": time.time(),
            "fan_mode": self.last_fan_mode,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['preset_status'])
    def preset_status(self):
        """Get current preset (boost mode) - auto-published when preset_status event occurs"""
        return {
            "event": "preset_status",
            "timestamp": time.time(),
            "preset": self.last_preset,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['power_status'])
    def power_status(self):
        """Get current power consumption - auto-published when power_status event occurs"""
        return {
            "event": "power_status",
            "timestamp": time.time(),
            "power_consumption": self.last_power_consumption,
            "host": self.host
        }
    
    @status(auto_publish=True, trigger_on=['heartbeat_status'])
    def heartbeat_status(self):
        """Get heartbeat status - auto-published when heartbeat_status event occurs"""
        return self.last_heartbeat or {
            "event": "heartbeat_status",
            "timestamp": time.time(),
            "status": "unknown",
            "host": self.host
        }
    
    @status()
    def device_capabilities(self):
        """Get device capabilities including temperature limits"""
        if not self.climate_entities:
            return None
    
    async def disconnect(self):
        """Disconnect from ESPHome device"""
        try:
            if self._state_subscription_task and not self._state_subscription_task.done():
                self._state_subscription_task.cancel()
                try:
                    await self._state_subscription_task
                except asyncio.CancelledError:
                    pass
            
            if self.client and self.connected:
                await self.client.disconnect()
                self.connected = False
                logging.info(f"Disconnected from ESPHome device {self.host}")
        except Exception as e:
            logging.error(f"Error disconnecting from ESPHome device {self.host}: {e}")