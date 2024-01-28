# Remote Procedure Call over Redis

This library provides an RPC implementation over Redis.   
To forward a request from the client to the service for the execution of the method, 
`Redis Streams` is used together with `Consumer Groupss` to distribute requests.  
To forward the result of the method execution from the service to the client, 
`Redis PubSub` is used with unique client and request identifiers


## Features
- Transparent forwarding of arguments and return value
- Supports/forces the use of Python type hints
- Built-in consistency check client-side with the server-side
- Supports multiple server-side instances at the same time, balancing via Redis
- Zeroconf, does not require open ports, addresses, HTTP API implementation, etc. Only Redis.
- Uses the built-in capabilities of Redis 5.0+ to forwarding in both directions

## Installation
```pip install rpc-over-redis```

## Using

First, you need to declare the server-side (service) app:  
`server.py`
```python
import os
from rpc_over_redis.core import RPCOverRedisService

redis_url = os.environ['REDIS_URL']     # REDIS_URL=redis://:password@redis/0

# initializing server-side
r = RPCOverRedisService(
    redis_url,
    'SmartEchoService'
)

@r.register
def echo() -> None:
    print('echo is called')
    pass

r.run_forever()
```

Then, you need to create a header class with empty methods.  
Now you can use it like a regular class. The arguments and the return value will be transparently passed through Redis
```python
import os
from rpc_over_redis.core import RPCOverRedisClient

class SmartEchoService(RPCOverRedisClient):
    def __init__(self, conn_url: str):
        super().__init__(conn_url, self.__class__.__name__, strict_validate_schema=True)

    def echo(self) -> None:
        ...

# initializing client-side
client = SmartEchoService(os.environ['REDIS_URL'])       # REDIS_URL=redis://:password@redis/0

# execute remote methods as local class methods...
client.echo()  # none returned
```

More examples see [here](https://github.com/mark99i/rpc-over-redis/tree/master/examples)

## Additional options
// TODO

## Limitations
- Only built-in types that allow to be converted to json/string should be used as arguments and return values.