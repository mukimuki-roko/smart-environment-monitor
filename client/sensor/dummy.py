import random


def dummy_dht22():
    tempe = random.uniform(23.0, 30.0)
    humid = random.uniform(39.0, 60.0)
    return round(tempe, 1), round(humid,1)


def dummy_bme280():
    pressure = random.uniform(900.0, 1400.0)
    return round(pressure, 1),


def dummy_mhz19c():
    co2 = random.uniform(500, 800)
    return round(co2),


def get_dummy_data():
    tempe, humid = dummy_dht22()
    pressure = dummy_bme280()
    co2 = dummy_mhz19c()

    return {
        "temperature": tempe,
        "humidity": humid,
        "pressure": pressure,
        "co2": co2
    }
