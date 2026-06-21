import serial
import time


class MHZ19CSensor:

    def __init__(self):
        try:
            self.ser = serial.Serial(
                port="/dev/serial0",
                baudrate=9600,
                timeout=2
            )
            print("MH-Z19C Ready")

        except Exception as e:
            print(f"Initialize Error : {e}")
            self.ser = None

    def read(self):

        if self.ser is None:
            return {"co2": None}

        try:
            command = bytes([
                0xFF, 0x01, 0x86,
                0x00, 0x00, 0x00,
                0x00, 0x00, 0x79
            ])

            self.ser.reset_input_buffer()

            self.ser.write(command)

            time.sleep(0.1)

            data = self.ser.read(9)

            print("Receive :", data.hex(" "))

            if len(data) != 9:
                return {"co2": None}

            co2 = data[2] * 256 + data[3]

            return {
                "co2": co2
            }

        except Exception as e:
            print(f"Read Error : {e}")
            return {
                "co2": None
            }


if __name__ == "__main__":

    sensor = MHZ19CSensor()

    while True:

        data = sensor.read()

        print(f"CO2 : {data['co2']} ppm")

        time.sleep(3)