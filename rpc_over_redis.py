import uuid
from abc import ABC
from types import FunctionType
from typing import Any, Callable
from urllib.parse import urlparse, ParseResult
from uuid import UUID

import redis

class RPCOverRedis(ABC):
    instance: redis.Redis | None
    service: str

    class RedisConnectionParams:
        host: str
        port: int
        password: str
        db: int
        decode_responses: bool
        socket_connect_timeout: int

        def __init__(self, conn_url: str):
            db_settings: ParseResult = urlparse(conn_url)
            self.host = db_settings.hostname
            self.port = int(db_settings.port or 6379)
            self.password = db_settings.password
            self.db = int(db_settings.path[1:])
            self.decode_responses = True
            self.socket_connect_timeout = 3

    def __init__(self, conn_url: str, service: str):
        self._methods = {}
        self.service = service
        # params = RPCOverRedis.RedisConnectionParams(conn_url)
        # self.instance = redis.Redis(**params.__dict__)
        # self.instance.ping()

class RPCOverRedisService(RPCOverRedis):
    _methods: dict[str, Callable[[dict, ], dict | None]]

    def register(self, handler: FunctionType):
        print(handler.__name__, handler)
        self._methods[handler.__name__] = handler
        return handler

    def _call_rpc(self, method: str, params: dict) -> dict:
        return self._methods[method](params)

class RPCOverRedisClient(RPCOverRedis):
    def __init__(self, conn_url: str, service: str):
        super().__init__(conn_url, service)
        self._rpc_reassign_methods()

    def _rpc_reassign_methods(self):
        methods = {x: y for x, y in self.__class__.__dict__.items() if
                   type(y) == FunctionType and not x.startswith('__')}

        def mistic(params: dict) -> dict:
            print('mistic', params['params']['args'], params['params']['kwargs'])
            return {
                'method': params['method'],
                'result': {'aaa': 1},
                'uuid': params['uuid'],
            }

        def m_modificator(m_name: str, annotations) -> Callable:
            def replaced_f(*args, **kwargs):
                pre_f = methods.get(f'_{m_name}_pre')
                post_f = methods.get(f'_{m_name}_post')

                args = (self, *args)
                args, kwargs = pre_f(*args, **kwargs) if pre_f else (args, kwargs)

                resp: dict = mistic({
                    'method': m_name,
                    'params': {
                        'args': list(args),
                        'kwargs': kwargs
                    },
                    'uuid': uuid.uuid4().hex
                })
                resp = resp['result']

                resp = post_f(resp) if post_f else resp
                return resp

            return replaced_f

        for name, handler in methods.items():
            print(handler.__annotations__, handler.__kwdefaults__, handler.__dict__, handler.__closure__, handler.__code__)

            if handler.__defaults__:
                default_values = dict(zip(handler.__code__.co_varnames[-len(handler.__defaults__):], handler.__defaults__))
                print(default_values)

            setattr(self, name, m_modificator(name, handler.__annotations__))

class Calculator(RPCOverRedisClient):
    def __init__(self, conn_url: str):
        super().__init__(conn_url, 'calculator')

    def sda(self, sd: int, h: float = 1.9, ds: float = None) -> tuple[float, float]:
        ...

    def _sda_pre(self, *args, **kwargs):
        print('pre exec', args, kwargs)
        return list(args), dict(kwargs)


c = Calculator('')
print(c.sda(1, 1.2, 2.3))
print()
print()
print(c.sda(1, 1.2, ds=2.3))


# def aaa(*args, **kwargs):
#     print(list(args))
#     print(kwargs)
#
#     print([*args, kwargs])
#
#
# aaa(1, 2, 's', 'fd', asd=12)