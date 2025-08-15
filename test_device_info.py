#!/usr/bin/env python3
"""
ESPHome Device Info Test Script
Repeatedly calls device_info() to test connection stability
"""

import asyncio
import logging
import time
from datetime import datetime
from aioesphomeapi import APIClient, APIConnectionError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('esphome_test.log')
    ]
)

class ESPHomeConnectionTester:
    def __init__(self, host, port=6053, password=None):
        self.host = host
        self.port = port
        self.password = password
        self.client = None
        self.connected = False
        self.test_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.start_time = time.time()
        
    async def connect(self):
        """Initial connection to the device"""
        try:
            self.client = APIClient(self.host, self.port, self.password)
            await self.client.connect(login=True)
            self.connected = True
            
            # Get initial device info to verify connection
            # device_info = await self.client.device_info()
            # logging.info(f"✅ Connected to ESPHome device: {device_info.name} (v{device_info.esphome_version})")
            # logging.info(f"   MAC: {device_info.mac_address}")
            return True
            
        except APIConnectionError as e:
            logging.error(f"❌ Failed to connect to ESPHome device {self.host}: {e}")
            self.connected = False
            return False
        except Exception as e:
            logging.error(f"❌ Unexpected error connecting to {self.host}: {e}")
            self.connected = False
            return False
    
    async def test_device_info(self):
        """Test calling device_info() and return success/failure"""
        self.test_count += 1
        
        try:
            start_time = time.time()
            device_info = await self.client.device_info()
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            self.success_count += 1
            logging.info(f"✅ Test #{self.test_count}: device_info() success "
                        f"(Response time: {response_time:.1f}ms) - {device_info.name}")
            return True, response_time
            
        except APIConnectionError as e:
            self.failure_count += 1
            logging.error(f"❌ Test #{self.test_count}: APIConnectionError - {e}")
            self.connected = False
            return False, None
            
        except Exception as e:
            self.failure_count += 1
            logging.error(f"❌ Test #{self.test_count}: Unexpected error - {e}")
            return False, None
    
    async def reconnect(self):
        """Attempt to reconnect after a failure"""
        logging.info("🔄 Attempting to reconnect...")
        
        # Clean up old client
        if self.client:
            try:
                await self.client.disconnect()
            except:
                pass  # Ignore errors during cleanup
        
        # Create new client and connect
        return await self.connect()
    
    def print_stats(self):
        """Print current test statistics"""
        runtime = time.time() - self.start_time
        success_rate = (self.success_count / self.test_count * 100) if self.test_count > 0 else 0
        
        logging.info(f"📊 Stats after {runtime:.0f}s: "
                    f"Tests: {self.test_count}, "
                    f"Success: {self.success_count}, "
                    f"Failures: {self.failure_count}, "
                    f"Success Rate: {success_rate:.1f}%")
    
    async def run_test(self, test_interval=30, max_tests=None, reconnect_on_failure=True):
        """
        Run the continuous test
        
        Args:
            test_interval: Seconds between tests (default 30)
            max_tests: Maximum number of tests to run (None for infinite)
            reconnect_on_failure: Whether to attempt reconnection after failures
        """
        logging.info(f"🚀 Starting ESPHome device_info() test for {self.host}:{self.port}")
        logging.info(f"   Test interval: {test_interval}s")
        logging.info(f"   Max tests: {max_tests if max_tests else 'unlimited'}")
        logging.info(f"   Reconnect on failure: {reconnect_on_failure}")
        
        # Initial connection
        if not await self.connect():
            logging.error("Failed to establish initial connection. Exiting.")
            return
        
        try:
            while max_tests is None or self.test_count < max_tests:
                # Run the test
                success, response_time = await self.test_device_info()
                
                # Handle failure
                if not success and reconnect_on_failure:
                    reconnect_success = await self.reconnect()
                    if reconnect_success:
                        # Try the test again after successful reconnection
                        success, response_time = await self.test_device_info()
                
                # Print stats every 10 tests or after failures
                if self.test_count % 10 == 0 or not success:
                    self.print_stats()
                
                # Wait before next test (unless it's the last test)
                if max_tests is None or self.test_count < max_tests:
                    await asyncio.sleep(test_interval)
                    
        except KeyboardInterrupt:
            logging.info("🛑 Test interrupted by user")
        except Exception as e:
            logging.error(f"💥 Unexpected error in test loop: {e}")
        finally:
            # Final stats
            self.print_stats()
            
            # Cleanup
            if self.client and self.connected:
                try:
                    await self.client.disconnect()
                    logging.info("🔌 Disconnected from device")
                except:
                    pass

async def main():
    """Main function - configure your ESPHome device details here"""
    
    # 🔧 CONFIGURE THESE VALUES FOR YOUR DEVICE
    HOST = "10.1.1.175"  # Replace with your ESPHome device IP
    PORT = 6053              # Default ESPHome API port
    PASSWORD = None          # Set to your API password if required, or None
    
    # Test configuration
    TEST_INTERVAL = 5       # Seconds between tests
    MAX_TESTS = None         # None for unlimited, or set a number like 100
    RECONNECT_ON_FAILURE = True  # Whether to try reconnecting after failures
    
    # Create and run the tester
    tester = ESPHomeConnectionTester(HOST, PORT, PASSWORD)
    await tester.run_test(
        test_interval=TEST_INTERVAL,
        max_tests=MAX_TESTS,
        reconnect_on_failure=RECONNECT_ON_FAILURE
    )

if __name__ == "__main__":
    print("ESPHome Connection Stability Tester")
    print("=" * 40)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test stopped by user")
    except Exception as e:
        print(f"💥 Fatal error: {e}")