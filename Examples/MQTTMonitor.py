#!/usr/bin/env python3
"""
Simple MQTT monitor to see all traffic on your thermostat network.
This will show you exactly what messages are being sent and received.
"""

import asyncio
import aiomqtt
import json
import sys
from datetime import datetime

class MQTTMonitor:
    def __init__(self, broker_host="localhost", broker_port=1883, username=None, password=None):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.message_count = 0
        
    async def start_monitoring(self, topics_to_monitor=None):
        """Start monitoring MQTT traffic"""
        if topics_to_monitor is None:
            topics_to_monitor = ["#"]  # Subscribe to everything
        
        try:
            print(f"🔍 Starting MQTT monitor")
            print(f"📡 Broker: {self.broker_host}:{self.broker_port}")
            print(f"📋 Topics: {topics_to_monitor}")
            print("=" * 80)
            
            client_args = {
                'hostname': self.broker_host,
                'port': self.broker_port,
            }
            
            if self.username and self.password:
                client_args['username'] = self.username
                client_args['password'] = self.password
                print(f"🔐 Using authentication: {self.username}")
            
            async with aiomqtt.Client(**client_args) as client:
                print("✅ Connected to MQTT broker")
                
                # Subscribe to topics
                for topic in topics_to_monitor:
                    await client.subscribe(topic)
                    print(f"📡 Subscribed to: {topic}")
                
                print("🎯 Monitoring started - Press Ctrl+C to stop")
                print("=" * 80)
                
                # Monitor messages
                async for message in client.messages:
                    await self._handle_message(message)
                    
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    async def _handle_message(self, message):
        """Handle incoming MQTT message"""
        self.message_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        topic = message.topic.value
        
        try:
            # Try to decode as JSON for pretty printing
            try:
                payload = json.loads(message.payload.decode())
                payload_str = json.dumps(payload, indent=2)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fall back to raw bytes if not JSON or not decodable
                try:
                    payload_str = message.payload.decode('utf-8')
                except UnicodeDecodeError:
                    payload_str = f"<binary data: {len(message.payload)} bytes>"
            
            # Color coding based on topic patterns
            if '/status/' in topic:
                color = "🟢"  # Green for status updates
            elif '/command' in topic or topic.endswith(('on', 'off', 'set_speed', 'read_temp')):
                color = "🔵"  # Blue for commands
            elif 'error' in topic.lower():
                color = "🔴"  # Red for errors
            else:
                color = "⚪"  # White for other
            
            print(f"{color} [{self.message_count:04d}] {timestamp}")
            print(f"📍 Topic: {topic}")
            print(f"📦 Payload: {payload_str}")
            print("-" * 40)
            
        except Exception as e:
            print(f"❌ Error processing message: {e}")

def main():
    """Main function"""
    print("🌡️  Thermostat MQTT Monitor")
    print("=" * 40)
    
    # Configuration - update these for your setup
    BROKER_HOST = "localhost"
    BROKER_PORT = 1883
    USERNAME = "scrumpi"  # Set if needed
    PASSWORD = "Th3rm"  # Set if needed
    
    # Topics to monitor - customize as needed
    TOPICS = [
        "#",  # Everything (comment this out if you want to be more specific)
        # "therm/#",  # Only thermostat messages
        # "devices/#",  # Only device messages
        # "+/+/+/status/+",  # Only status messages
        # "+/+/+/+",  # Commands
    ]
    
    # Allow command line override of broker
    if len(sys.argv) > 1:
        BROKER_HOST = sys.argv[1]
        print(f"📡 Using broker from command line: {BROKER_HOST}")
    
    # Create and start monitor
    monitor = MQTTMonitor(
        broker_host=BROKER_HOST,
        broker_port=BROKER_PORT,
        username=USERNAME,
        password=PASSWORD
    )
    
    try:
        asyncio.run(monitor.start_monitoring(TOPICS))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()