import RPi.GPIO as GPIO

class GPIOManager:
    _instance = None
    _pins_in_use = set()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            GPIO.setmode(GPIO.BCM)
        return cls._instance
    
    def reserve_pin(self, pin):
        if pin in self._pins_in_use:
            raise ValueError(f"Pin {pin} already in use")
        self._pins_in_use.add(pin)
    
    def release_pin(self, pin):
        self._pins_in_use.discard(pin)
        GPIO.cleanup(pin)
