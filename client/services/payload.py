import datetime

from config import CLIENT_ID, CLIENT_REGION, SERVER_ADDR, SERVER_PORT
from utils.data_class import SensorData, ServerSendData


def build_payload(sensor_data: SensorData) -> ServerSendData:
    return {
        "client_id": CLIENT_ID,
        "region": CLIENT_REGION,
        "datetime": datetime.datetime.now().isoformat(),
        "sensor_data": sensor_data,
    }


def build_server_disconnect_error_embed(
    data: ServerSendData, server_addr=None, server_port=None
) -> dict:
    server_addr = server_addr or SERVER_ADDR
    server_port = server_port or SERVER_PORT
    sensor_data = data["sensor_data"]

    return {
        "embeds": [
            {
                "title": "Server disconnect error",
                "description": "Failed server connection",
                "color": 0xE74C3C,
                "fields": [
                    {
                        "name": "Server",
                        "value": f"{server_addr}:{server_port}",
                        "inline": False,
                    },
                    {
                        "name": "Client Region",
                        "value": f'{data["region"]}',
                        "inline": True,
                    },
                    {
                        "name": "Client ID",
                        "value": f'{data["client_id"]}',
                        "inline": True,
                    },
                    {
                        "name": "Datetime",
                        "value": data["datetime"],
                        "inline": False,
                    },
                    {
                        "name": "Sensor Data",
                        "value": (
                            f'Temperature: {sensor_data["temperature"]}\n'
                            f'Humidity: {sensor_data["humidity"]}\n'
                            f'Pressure: {sensor_data["pressure"]}\n'
                            f'CO2: {sensor_data["co2"]}'
                        ),
                        "inline": False,
                    },
                ],
            }
        ]
    }
