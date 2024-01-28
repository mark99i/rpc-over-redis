import logging
import os
import random
import uuid

from dotenv import load_dotenv
from rpc_over_redis.core import RPCOverRedisClient


class SmartEchoService(RPCOverRedisClient):
    def __init__(self, conn_url: str):
        super().__init__(conn_url, self.__class__.__name__, strict_validate_schema=True)

    def echo(self) -> None:
        ...

    def give_me_str(self) -> str:
        ...

    def give_me_dict(self) -> dict:
        ...

    def verify_list_dict(self, my_list: list, my_dict: dict) -> bool:
        ...

    def some_magic(self, a: int, b: int) -> str:
        ...


load_dotenv()  # load .env REDIS_URL: redis://:password@redis/0

# initializing info log
logging.basicConfig()
logging.getLogger('RPCSmartEchoService').setLevel(logging.INFO)

# initializing client-side
client = SmartEchoService(os.environ['REDIS_URL'])

# execute remote methods as local class methods...
client.echo()  # none returned

_ = client.give_me_str()
print(_)  # test string returned
assert _ == 'some test string'

_ = client.give_me_dict()
print(_)  # test dict returned
assert _ == {'num1': 1, 'num2': [1, 2, 3], 'num3': True, 'num4': ['s', 1, True], 'num5': 1.4}

_ = client.verify_list_dict([1, 2], {'a': 1})
print(_)  # returned True
assert _

_a, _b = random.randint(10, 1000000), random.randint(10, 10000000)
_ = client.some_magic(_a, _b)
print(_)  # returned result of some_magic() on server-side
assert _ == uuid.UUID(int=_a*_b).hex
