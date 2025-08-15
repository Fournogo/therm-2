import asyncio
import logging
from typing import Type, TypeVar
import time

SM = TypeVar("SM", bound="StinkMode")

class StinkMode:
    _instance = None

    def __new__(cls: Type[SM], *args, **kwargs) -> SM:
        """
        Ensures a single instance of this object (singleton pattern).
        Note: In async context, singleton is less critical since we control instantiation
        """
        if not cls._instance:
            cls._instance = super(StinkMode, cls).__new__(cls)
        return cls._instance
    
    def __init__(self: SM, controller=None, state_manager=None, config=None) -> None:
        """
        Run when initializing the object. Initialize queues and state.
        Only initializes once due to singleton pattern.
        """
        if hasattr(self, '_initialized'):
            return
            
        if controller is None:
            raise ValueError("Controller must be provided on initialization")
        
        if config is None:
            raise ValueError("Config must be provided on first initialization")

        self.config = config
        self.controller = controller
        self.state_manager = state_manager

        self.previous_states = {}

        self.timeout = config.get('timeout', 300)
        self.device_name = config.get('device_name', 'stink_button')
        self.timer_task = None
        self._toggle_in_progress = False
        
        asyncio.create_task(self.button_monitor())

        # Mark as initialized
        self._initialized = True

    async def button_monitor(self):
        """Function for continuously monitoring button status and performing the appropriate action upon a press."""
        
        # Get the stink button from your config
        try:
            stink_button = self.controller.get_device(self.device_name)
            if not stink_button:
                logging.error(f"❌ Device '{self.device_name}' not found")
                return
                
            button_component = stink_button.button
        except Exception as e:
            logging.error(f"❌ Error getting stink button device: {e}")
            return
        
        while True:
            try:
                # Wait for button press status (30 second timeout)
                if await button_component.wait_for_status('pressed_status', timeout=30):
                    # Get the button press data
                    press_data = button_component.get_latest_status('pressed_status')
                    
                    if press_data and not self._toggle_in_progress:
                        press_count = press_data.get('press_count', 0)
                        timestamp = press_data.get('timestamp', 0)
                        pin = press_data.get('pin', 0)
                        
                        # Prevent overlapping toggles by using await instead of create_task
                        self._toggle_in_progress = True
                        try:
                            await self.toggle_stink_mode()
                        finally:
                            self._toggle_in_progress = False
                    
                    # Clear the event
                    # button_component.clear_status_event('pressed_status')
                    
                else:
                    logging.debug("⏰ No button press in the last 30 seconds")
                    
            except KeyboardInterrupt:
                logging.info("Button monitoring stopped")
                break
            except Exception as e:
                logging.error(f"Error in button monitoring: {e}")
                await asyncio.sleep(1)

    async def toggle_stink_mode(self):
        """Toggle stink mode on or off"""
        try:
            current_state = self.state_manager.get_state('stink_mode')
            if current_state is True:
                logging.info("Stink mode currently running... Disabling it.")
                await self.stink_mode_off()
            elif current_state is False:
                logging.info("Enabling stink mode...")
                await self.stink_mode_on()
            else:
                # State not found or None - assume off and turn on
                logging.info("Stink mode state unknown, enabling it...")
                await self.stink_mode_on()
        except Exception as e:
            logging.error(f"Error in toggle_stink_mode: {e}")

    async def stink_mode_on(self):
        """Turn on stink mode with better error handling"""
        # Set state first
        try:
            await self.state_manager.set_state('stink_mode', True)
        except Exception as e:
            logging.error(f"Error setting stink_mode state: {e}")
            return
        
        # Cancel any existing timer
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
        
        # Start new timer task (non-blocking)
        self.timer_task = asyncio.create_task(self._auto_off_timer(self.timeout))
        logging.info(f"Stink mode auto-off timer started for {self.timeout} seconds")

        timeout_end_time = time.time() + self.timeout
        try:
            await self.state_manager.set_state('stink_mode_end', int(timeout_end_time * 1000))
        except Exception as e:
            logging.error(f"Error setting stink_mode timer end time: {e}")
            return

        # Get devices with error handling
        try:
            stink_button = self.controller.get_device(self.device_name)
            if not stink_button:
                logging.error(f"❌ Device '{self.device_name}' not found")
                return
            
            hvac = self.controller.get_device("hvac")
            if not hvac:
                logging.error("❌ Device 'hvac' not found")
                return
        except Exception as e:
            logging.error(f"❌ Error getting devices: {e}")
            return

        # Store previous states before making changes
        try:
            self.previous_states["fan_power"] = self.state_manager.get_state("hvac.fan.fan_status")["power"]
            self.previous_states["bathroom_valve"] = self.state_manager.get_state("hvac.bathroom_valve.relay_status")["relay"]
            self.previous_states["avery_valve"] = self.state_manager.get_state("hvac.avery_valve.relay_status")["relay"]
            logging.debug(f"Stored previous states: {self.previous_states}")
        except Exception as e:
            logging.error(f"❌ Error storing previous states: {e}")
            # Continue anyway with default values
            self.previous_states = {
                "fan_power": 5,  # Default fan power
                "bathroom_valve": False,
                "avery_valve": True
            }

        # Apply stink mode settings
        try:
            await hvac.bathroom_valve.on()
            await hvac.avery_valve.off()
            await hvac.fan.set_power(power=10)
            await stink_button.light.on()
            logging.info("✅ Stink mode activated successfully")
        except Exception as e:
            logging.error(f"❌ Error applying stink mode settings: {e}")

    async def stink_mode_off(self):
        """Turn off stink mode with better error handling"""
        # Set state first
        try:
            await self.state_manager.set_state('stink_mode', False)
        except Exception as e:
            logging.error(f"Error setting stink_mode state: {e}")
            return
        
        # Cancel the timer if it's running
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            logging.info("Stink mode timer cancelled")

        try:
            await self.state_manager.set_state('stink_mode_end', None)
        except Exception as e:
            logging.error(f"Error setting stink_mode timer end time to None: {e}")
            return

        # Get devices with error handling
        try:
            stink_button = self.controller.get_device(self.device_name)
            if not stink_button:
                logging.error(f"❌ Device '{self.device_name}' not found")
                return
            
            hvac = self.controller.get_device("hvac")
            if not hvac:
                logging.error("❌ Device 'hvac' not found")
                return
        except Exception as e:
            logging.error(f"❌ Error getting devices: {e}")
            return

        # Restore previous states
        try:
            # Fix the valve logic - restore to actual previous states
            if self.previous_states.get("bathroom_valve") is True:
                await hvac.bathroom_valve.on()
            else:
                await hvac.bathroom_valve.off()

            if self.previous_states.get("avery_valve") is True:
                await hvac.avery_valve.on()
            else:
                await hvac.avery_valve.off()

            await hvac.fan.set_power(power=self.previous_states.get("fan_power", 5))
            await stink_button.light.off()
            
            logging.info("✅ Stink mode deactivated successfully")
            logging.debug(f"Restored states: {self.previous_states}")
        except Exception as e:
            logging.error(f"❌ Error restoring previous states: {e}")
        
    async def _auto_off_timer(self, seconds):
        """Internal timer function that waits then turns off"""
        try:
            await asyncio.sleep(seconds)
            # Timer completed without being cancelled
            logging.info(f"Timer expired after {seconds} seconds - auto turning off")
            await self.stink_mode_off()
        except asyncio.CancelledError:
            # Timer was cancelled (system turned off manually)
            logging.debug("Timer was cancelled")
            raise  # Re-raise so the task knows it was cancelled