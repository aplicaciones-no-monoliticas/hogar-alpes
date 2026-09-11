import datetime
import time


def time_millis() -> int:
    return int(time.time() * 1000)


def unix_time_millis(dt: datetime.datetime) -> int:
    epoch = datetime.datetime.utcfromtimestamp(0)
    return int((dt - epoch).total_seconds() * 1000.0)
