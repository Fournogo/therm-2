#!/usr/bin/env python3
"""
Device service runner - keeps MQTT clients alive
"""

import sys
import time
import signal
import logging
import os
from ComponentFactory import DeviceManager

class DeviceService:
    def __init__(self, config_file):
        self.config_file = config_file
        self.device_manager = None
        self.running = True
        
        # Setup logging with fallback locations
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def _setup_logging(self):
        """Setup logging with relative paths based on script location"""
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create logs directory relative to script location
        log_dir = os.path.join(script_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Log file in the logs subdirectory
        log_file = os.path.join(log_dir, 'device_service.log')
        
        try:
            # Test if we can write to the log file
            with open(log_file, 'a') as test_file:
                pass
            
            handlers = [
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
            print(f"Logging to: {log_file}")
            
        except (PermissionError, OSError) as e:
            # Fallback to console only
            handlers = [logging.StreamHandler(sys.stdout)]
            print(f"Warning: Could not create log file ({e}), logging to console only")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def start(self):
        """Start the device service"""
        try:
            self.logger.info(f"Starting device service with config: {self.config_file}")
            
            # Initialize the device manager
            self.device_manager = DeviceManager(self.config_file)
            
            self.logger.info("Device manager initialized successfully")
            self.logger.info("MQTT clients are running...")
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Error in device service: {e}")
            raise
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        if self.device_manager:
            self.logger.info("Cleaning up device manager...")
            self.device_manager.cleanup_all()
        self.logger.info("Device service stopped")

def main():
    """Main entry point"""
    if len(sys.argv) != 2:
        print("Usage: python3 device_service.py <config.yaml>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    service = DeviceService(config_file)
    service.start()

if __name__ == "__main__":
    main()