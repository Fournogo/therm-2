#!/usr/bin/env python3
# debug_heartbeat.py - Debug why heartbeats aren't showing in state

import asyncio
import logging
import yaml

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

async def debug_heartbeat():
    """Debug heartbeat functionality"""
    
    print("=== Debugging Heartbeat System ===\n")
    
    try:
        from ConfigLoader import create_device_controller
        from State import create_state_manager
        
        # 1. Create controller
        print("1. Creating device controller...")
        controller = await create_device_controller(
            config_directory="configs",
            component_path="."
        )
        
        # 2. Check MQTT managers
        print("\n2. Checking MQTT managers...")
        if hasattr(controller, 'mqtt_managers'):
            print(f"   Found {len(controller.mqtt_managers)} MQTT managers:")
            for prefix, manager in controller.mqtt_managers.items():
                print(f"   - {prefix}: {manager}")
                print(f"     Connected: {manager.is_connected}")
                print(f"     Heartbeat request topic: {manager.heartbeat_request_topic}")
                print(f"     Heartbeat response topic: {manager.heartbeat_response_topic}")
        else:
            print("   ERROR: Controller has no mqtt_managers attribute!")
        
        # 3. Send test heartbeats directly
        print("\n3. Sending test heartbeats directly...")
        for prefix, manager in controller.mqtt_managers.items():
            print(f"\n   Sending heartbeat for {prefix}...")
            result = await manager.send_heartbeat()
            print(f"   Send result: {result}")
            
            # Wait for response
            await asyncio.sleep(2)
            
            # Check if we got a response
            latest = manager.get_latest_heartbeat()
            print(f"   Latest heartbeat data: {latest}")
        
        # 4. Create state manager
        print("\n4. Creating state manager...")
        with open('config.yaml', 'r') as f:
            app_config = yaml.safe_load(f)
        
        state_config = app_config.get('state', {})
        state_manager = await create_state_manager(controller, state_config)
        
        # 5. Check heartbeat definitions
        print("\n5. Checking heartbeat definitions...")
        print(f"   Found {len(state_manager.heartbeat_definitions)} heartbeat definitions:")
        for hb_def in state_manager.heartbeat_definitions:
            print(f"   - {hb_def}")
        
        # 6. Start state monitoring
        print("\n6. Starting state monitoring...")
        await state_manager.start_continuous_refresh()
        
        # Wait for initial refresh
        await asyncio.sleep(5)
        
        # 7. Check states
        print("\n7. Checking all states...")
        all_states = state_manager.get_all_states()
        
        print(f"\n   Total states: {len(all_states)}")
        
        # Look for heartbeat states
        heartbeat_states = {k: v for k, v in all_states.items() if 'heartbeat' in k}
        print(f"\n   Heartbeat states found: {len(heartbeat_states)}")
        for key, value in heartbeat_states.items():
            print(f"   - {key}: {value}")
        
        # 8. Monitor for updates
        print("\n8. Monitoring for heartbeat updates (30 seconds)...")
        
        update_count = 0
        start_time = asyncio.get_event_loop().time()
        
        async for state in state_manager.get_state_updates():
            # Check for heartbeat keys
            hb_keys = [k for k in state.keys() if 'heartbeat' in k]
            if hb_keys:
                update_count += 1
                elapsed = asyncio.get_event_loop().time() - start_time
                print(f"\n   Heartbeat update #{update_count} at {elapsed:.1f}s:")
                for key in hb_keys:
                    print(f"   - {key}: {state[key]}")
            
            if asyncio.get_event_loop().time() - start_time > 30:
                break
        
        # Cleanup
        await state_manager.stop_continuous_refresh()
        await controller.disconnect_all()
        
    except Exception as e:
        print(f"\n❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_heartbeat())