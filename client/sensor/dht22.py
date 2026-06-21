from sensor.dht22_takemoto import (
    DHT22,
    DHT22CRCError,
    DHT22MissingDataError
)


class DHT22Sensor:
    def __init__(self, gpio=4):
        """
        DHT22の初期化
        """
        self.sensor = DHT22(gpio)

    def read(self):
        """
        温度・湿度を取得

        Returns:
            {
                "temperature": 温度,
                "humidity": 湿度
            }

            エラー時: None
        """
        try:
            temperature, humidity, _ = self.sensor.read()

            return {
                "temperature": round(temperature, 1),
                "humidity": round(humidity, 1)
            }

        except (DHT22CRCError, DHT22MissingDataError) as e:
            print(f"DHT22 Error: {e}")
            return None

        except Exception as e:
            print(f"DHT22 Error: {e}")
            return None

    def close(self):
        self.sensor.close()


if __name__ == "__main__":
    sensor = DHT22Sensor(gpio=26)

    try:
        while True:
            data = sensor.read()
            print(data)

            import time
            time.sleep(3)

    except KeyboardInterrupt:
        print("終了します。")

    finally:
        sensor.close()