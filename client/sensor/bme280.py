import time
import board
import busio
from adafruit_bme280 import basic as adafruit_bme280


class BME280Sensor:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)

        self.sensor = adafruit_bme280.Adafruit_BME280_I2C(
            i2c,
            address=0x76
        )

    def read(self):
        try:
            return {
                "pressure": round(self.sensor.pressure, 1)
            }

        except Exception as e:
            print(f"BME280 Error: {e}")
            return {
                "pressure": None
            }


if __name__ == "__main__":
    sensor = BME280Sensor()

    try:
        while True:
            data = sensor.read()

            print(f"Pressure    : {data['pressure']} hPa")
            print()

            time.sleep(3)

    except KeyboardInterrupt:
        print("終了")