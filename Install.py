#!/usr/bin/env python3
"""
Device Environment Installer
Ensures all required packages are installed for the IoT device system
"""

import subprocess
import sys
import os
import importlib
from pathlib import Path

class DeviceInstaller:
    def __init__(self):
        self.required_packages = self._get_required_packages()
        self.system_packages = self._get_system_packages()
        
    def _get_required_packages(self):
        """
        Define all required Python packages
        Format: 'package_name': 'pip_install_name'
        """
        return {
            # MQTT and networking
            'paho.mqtt.client': 'paho-mqtt',
            'zeroconf': 'zeroconf',
            
            # Hardware interfaces (Raspberry Pi)
            'RPi.GPIO': 'RPi.GPIO',
            'smbus': 'smbus',
            'board': 'adafruit-circuitpython-busdevice',
            
            # Sensor libraries
            'adafruit_sht31d': 'adafruit-circuitpython-sht31d',
            'adafruit_tca9548a': 'adafruit-circuitpython-tca9548a',
            'adafruit_shtc3': 'adafruit-circuitpython-shtc3', 
            'adafruit_dps310': 'adafruit-circuitpython-dps310',
            
            # Data and web
            'yaml': 'PyYAML',
            'requests': 'requests',
            'influxdb_client': 'influxdb-client',
            
            # Standard packages (usually included but just in case)
            'json': None,  # Built-in
            'time': None,  # Built-in
            'threading': None,  # Built-in
            'logging': None,  # Built-in
        }
    
    def _get_system_packages(self):
        """
        System packages that might need to be installed via apt
        """
        return [
            'python3-pip',
            'python3-venv', 
            'i2c-tools',
            'python3-dev',
            'build-essential'
        ]
    
    def check_python_version(self):
        """Check if Python version is compatible"""
        version = sys.version_info
        print(f"Python version: {version.major}.{version.minor}.{version.micro}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 7):
            print("❌ Python 3.7+ required")
            return False
        
        print("✅ Python version OK")
        return True
    
    def check_virtual_environment(self):
        """Check if running in a virtual environment"""
        in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        
        if in_venv:
            print(f"✅ Running in virtual environment: {sys.prefix}")
        else:
            print("⚠️  Not in virtual environment")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Recommendation: Create a virtual environment first:")
                print("  python3 -m venv venv")
                print("  source venv/bin/activate")
                print("  python install_devices.py")
                return False
        
        return True
    
    def install_package(self, package_name, pip_name):
        """Install a single package using pip"""
        if pip_name is None:
            print(f"⏭️  {package_name} is built-in, skipping")
            return True
            
        try:
            print(f"📦 Installing {pip_name}...")
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install', pip_name, '--upgrade'
            ], capture_output=True, text=True, check=True)
            
            print(f"✅ {pip_name} installed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {pip_name}")
            print(f"   Error: {e.stderr}")
            return False
    
    def check_package_import(self, package_name):
        """Test if a package can be imported"""
        try:
            importlib.import_module(package_name)
            print(f"✅ {package_name} imports successfully")
            return True
        except ImportError:
            print(f"❌ {package_name} cannot be imported")
            return False
    
    def install_all_packages(self):
        """Install all required packages"""
        print("\n=== Installing Python Packages ===")
        
        failed_packages = []
        
        for package_name, pip_name in self.required_packages.items():
            success = self.install_package(package_name, pip_name)
            if not success:
                failed_packages.append(package_name)
        
        return failed_packages
    
    def verify_installations(self):
        """Verify all packages can be imported"""
        print("\n=== Verifying Package Imports ===")
        
        failed_imports = []
        
        for package_name, pip_name in self.required_packages.items():
            if pip_name is not None:  # Skip built-ins
                success = self.check_package_import(package_name)
                if not success:
                    failed_imports.append(package_name)
        
        return failed_imports
    
    def check_hardware_permissions(self):
        """Check if user has permissions for hardware access"""
        print("\n=== Checking Hardware Permissions ===")
        
        # Check GPIO access
        gpio_path = Path('/dev/gpiomem')
        if gpio_path.exists():
            print("✅ GPIO device found")
        else:
            print("⚠️  GPIO device not found (normal on non-Pi systems)")
        
        # Check I2C access
        i2c_devices = list(Path('/dev').glob('i2c-*'))
        if i2c_devices:
            print(f"✅ I2C devices found: {[d.name for d in i2c_devices]}")
        else:
            print("⚠️  No I2C devices found")
            print("   You may need to enable I2C in raspi-config")
        
        # Check user groups
        try:
            import grp
            user_groups = [g.gr_name for g in grp.getgrall() if os.getenv('USER') in g.gr_mem]
            
            recommended_groups = ['gpio', 'i2c', 'spi']
            missing_groups = [g for g in recommended_groups if g not in user_groups]
            
            if missing_groups:
                print(f"⚠️  Consider adding user to groups: {missing_groups}")
                print("   sudo usermod -a -G gpio,i2c,spi $USER")
            else:
                print("✅ User has recommended group memberships")
                
        except Exception as e:
            print(f"⚠️  Could not check user groups: {e}")
    
    def create_test_script(self):
        """Create a simple test script to verify installation"""
        test_script = """#!/usr/bin/env python3
'''
Device Installation Test Script
'''

def test_imports():
    print("Testing critical imports...")
    
    try:
        import yaml
        print("✅ YAML support")
    except ImportError as e:
        print(f"❌ YAML: {e}")
    
    try:
        import paho.mqtt.client as mqtt
        print("✅ MQTT client")
    except ImportError as e:
        print(f"❌ MQTT: {e}")
    
    try:
        import requests
        print("✅ HTTP requests")
    except ImportError as e:
        print(f"❌ Requests: {e}")
    
    try:
        import RPi.GPIO as GPIO
        print("✅ GPIO support")
    except ImportError as e:
        print(f"⚠️  GPIO: {e} (normal on non-Pi systems)")
    
    print("\\nTest complete!")

if __name__ == "__main__":
    test_imports()
"""
        
        with open('test_installation.py', 'w') as f:
            f.write(test_script)
        
        os.chmod('test_installation.py', 0o755)
        print("✅ Created test_installation.py")
    
    def run_installation(self):
        """Run the complete installation process"""
        print("🚀 Device Environment Installer")
        print("=" * 40)
        
        # Check prerequisites
        if not self.check_python_version():
            return False
            
        if not self.check_virtual_environment():
            return False
        
        # Install packages
        failed_packages = self.install_all_packages()
        
        if failed_packages:
            print(f"\n❌ Failed to install: {failed_packages}")
            print("You may need to install system dependencies first:")
            print(f"sudo apt update && sudo apt install {' '.join(self.system_packages)}")
            return False
        
        # Verify installations
        failed_imports = self.verify_installations()
        
        if failed_imports:
            print(f"\n❌ Failed to import: {failed_imports}")
            return False
        
        # Additional checks
        self.check_hardware_permissions()
        self.create_test_script()
        
        print("\n🎉 Installation completed successfully!")
        print("\nNext steps:")
        print("1. Run: python test_installation.py")
        print("2. Configure your config.yaml files")
        print("3. Test with: python device_service.py config.yaml")
        
        return True

def main():
    installer = DeviceInstaller()
    success = installer.run_installation()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()