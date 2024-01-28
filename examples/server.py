import logging
import os
import uuid

from dotenv import load_dotenv

from rpc_over_redis.core import RPCOverRedisService

load_dotenv()  # load .env REDIS_URL: redis://:password@redis/0

# initializing info log
logging.basicConfig()
logging.getLogger('RPCSmartEchoService').setLevel(logging.INFO)

# initializing server-side
r = RPCOverRedisService(
    os.environ['REDIS_URL'],
    'SmartEchoService'
)


# registering method with none args and return None
@r.register
def echo() -> None:
    print('echo is called')
    pass


# registering method with none args and return str
@r.register
def give_me_str() -> str:
    return 'some test string'


# create func with random name and register this as 'give_me_dict' with origin types
def changed_func_name() -> dict:
    return {'num1': 1, 'num2': [1, 2, 3], 'num3': True, 'num4': ['s', 1, True], 'num5': 1.4}


r.register(changed_func_name, 'give_me_dict')


# create func and register this with origin name
def verify_list_dict(my_list: list, my_dict: dict) -> bool:
    assert my_list == [1, 2]
    assert my_dict == {'a': 1}
    return True


r.register(verify_list_dict)


# register lambda function with name 'some_magic' and custom type hinting
r.register(
    lambda a, b: uuid.UUID(int=a * b).hex,
    'some_magic',
    args={'a': int, 'b': int, 'return': str}
)


# wait requests
r.run_forever()
