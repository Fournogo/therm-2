import asyncio
import logging
from typing import Optional, Callable

class GlobalRegistry:
    """Global registry for system-wide objects and functions"""
    _state_manager = None
    _trigger_refresh_func: Optional[Callable] = None
    
    @classmethod
    def set_state_manager(cls, state_manager):
        """Register the state manager"""
        cls._state_manager = state_manager
        # Set up the trigger function
        if hasattr(state_manager, 'trigger_state_refresh'):
            cls._trigger_refresh_func = state_manager.trigger_state_refresh
        logging.info("StateManager registered in GlobalRegistry")
    
    @classmethod
    def get_state_manager(cls):
        """Get the registered state manager"""
        return cls._state_manager
    
    @classmethod
    def trigger_state_refresh(cls, status_path: str):
        """Trigger state refresh if available"""
        if cls._trigger_refresh_func:
            asyncio.create_task(cls._trigger_refresh_func(status_path))
        else:
            logging.warning(f"Cannot trigger state refresh for {status_path} - no state manager registered")
    
    @classmethod
    def is_available(cls):
        """Check if state manager is available"""
        return cls._state_manager is not None