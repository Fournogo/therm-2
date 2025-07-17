# Your credentials (you need to obtain these)

token = 'b5047379d30afe64f8095b2ed6765289c1f20322761365f1a556b327cab0772cf6af1a8527656c487ca3cdd79c02a273c50717e484c68e45d9b16a16bed4a141'
key = '8724592ecb24443485b25c242e204721942e4e7e9ead438fa90e20d1a837012b'
ip = '10.1.1.173'
id = 150633094591465

# token = '638dcba4dcb3f7da8b1cfe5e97746c18195c487ed0d7dd8271b17a0bdcf91542dd98296a266fb3c5386423e30a852547beb57646f47f682c4ef0535539fe5b74'
# key = 'b9736f858a424afdb89801bb43b11fae2091792821544dfeac34e93c935d5cb2'
# ip = '10.1.1.172'
# id = 151732606217683

import asyncio
from msmart.device import AirConditioner as AC

async def control_ac():
    # Create device (you'll get these values from the discover command)
    device = AC(ip=ip, 
                port=6444, 
                device_id=id,
                token=token,
                key=key)
    
    # Connect and get capabilities
    await device.get_capabilities()
    
    # Get current state
    await device.refresh()
    print(f"Current temp: {device.indoor_temperature}")
    print(f"Target temp: {device.target_temperature}")
    print(f"Power: {device.power_state}")
    
    # Control the device
    # device.power_state = True
    # device.target_temperature = 72
    # device.operational_mode = device.operational_modes.COOL
    # device.fan_speed = device.fan_speeds.HIGH
    
    # Apply changes
    await device.apply()

# Run it
asyncio.run(control_ac())