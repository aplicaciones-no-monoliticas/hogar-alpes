import os


def broker_host() -> str:
    return os.getenv('BROKER_HOST', 'localhost')
