import json
import logging
import math
import threading
import time
import uuid
from abc import ABC, ABCMeta
from types import FunctionType
from typing import Any, Callable

import redis

from rpc_types import RPCResponceMessage, RPCRequestMessageParams, RPCRequestMessage, RedisConnectionParams, RPCTimeoutError, RPCTypesMismatch, \
    RPCError, RPCImplementationError, RPCExecutionError


class RPCOverRedis(ABC):
    _rds: redis.Redis | None
    _instance_guid: str
    _service: str
    _running: bool
    _running_threads: list[threading.Thread]

    _logger: logging.Logger
    _key_prefix: str
    _remote_exec_timeout: int
    _protocol_version: int

    def __init__(
            self,
            conn_url: str,
            service: str,
            redis_instance: redis.Redis | None = None,
            instance_guid: str | None = None,
            key_prefix: str | None = None,
            remote_exec_timeout: int | None = None,
            protocol_version: int | None = None,
            logger: logging.Logger | None = None
    ):
        self._methods = {}
        self._service = service
        self._running = True
        self._running_threads = []
        self._instance_guid = instance_guid or uuid.uuid4().hex

        self._key_prefix = key_prefix or '/rpc-over-redis'
        self._remote_exec_timeout = remote_exec_timeout or 30000
        self._protocol_version = protocol_version or 1
        self._logger = logger or logging.getLogger(f'RPC{service}')

        self._rds = redis_instance or redis.Redis(**RedisConnectionParams(conn_url).__dict__)
        self._rds.ping()
        self._logger.debug('ping redis success')

    @property
    def logger(self) -> logging.Logger: return self._logger

    def close(self) -> None:
        self._running = False

    def __del__(self):
        self.close()


class RPCOverRedisService(RPCOverRedis):
    _registered_methods: dict[str, Callable | FunctionType]
    _registered_methods_args: dict[str, type | Any]
    _force_strict_validate_schema: bool
    _xread_groupname: str

    def __init__(
            self,
            conn_url: str,
            service: str,
            xread_groupname: str | None = None,
            force_strict_validate_schema: bool = False,
            **kwargs):
        super().__init__(conn_url, service, **kwargs)
        self._registered_methods = {}
        self._registered_methods_args = {}
        self._xread_groupname = xread_groupname or 'generic'
        self._force_strict_validate_schema = force_strict_validate_schema

        t = threading.Thread(target=self._subscribe_redis, daemon=True)
        t.start()
        self._running_threads.append(t)

    def register(self, handler: FunctionType | Callable, method_name: str | None = None, args: dict[str, type | Any] | None = None) -> Callable:
        args = args if args is not None else handler.__annotations__
        method_name = method_name or handler.__name__
        self._registered_methods[method_name] = handler
        self._registered_methods_args[method_name] = args
        self.logger.info(f"registered method '{method_name}' {str(handler)} {args}")
        return handler

    def run_forever(self) -> None:
        self.logger.debug("enter to run forever")
        try:
            while self._running: time.sleep(1000000)
        except (KeyboardInterrupt, SystemExit):
            pass

    def _subscribe_redis(self):
        def _handle_message(message: RPCRequestMessage):
            exc, responce = self._call_rpc(message.method, message.params)

            payload = RPCResponceMessage(**{
                'result': responce,
                'error': exc.dict() if exc is not None else None,
                'request': message.request
            })
            self._logger.debug(f'publish {self._key_prefix}/responce/{message.client} {payload.model_dump_json()}')
            self._rds.publish(f'{self._key_prefix}/responce/{message.client}', payload.model_dump_json())

        try:
            self._rds.xgroup_create(f'{self._key_prefix}/request/{self._service}', self._xread_groupname, mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "name already exists" not in str(e): raise

        while self._running:
            messages = self._rds.xreadgroup(
                self._xread_groupname,
                self._instance_guid,
                {f'{self._key_prefix}/request/{self._service}': '>'},
                count=1, block=1000, noack=True)

            for stream, message_list in messages:
                for _message in message_list:
                    message_id, message_data = _message
                    message_data: dict = json.loads(message_data['data'])
                    self._logger.debug(f'xreadgroup {self._key_prefix}/request/{self._service} {message_data}')

                    # FIXME: make responce to client
                    if message_data['protocol'] != self._protocol_version:
                        message_data_protocol = message_data['protocol']
                        raise RPCImplementationError(
                            f'message.protocol ({message_data_protocol}) != self._protocol_version ({self._protocol_version})'
                        )

                    _handle_message(RPCRequestMessage.model_validate(message_data))
                    self._rds.xack(f'{self._key_prefix}/request/{self._service}', self._xread_groupname, message_id)

    def _call_rpc(self, method: str, params: RPCRequestMessageParams) -> tuple[RPCError | None, dict | None]:
        if method == '_rpc_schema_':
            return None, {
                'force_strict_validate_schema': self._force_strict_validate_schema,
                'types': {
                    k: {
                        ik: (f'{iv.__module__}/{iv.__name__}' if iv is not None else 'builtins/NoneType')
                        for ik, iv in v.items()
                    }
                    for k, v in self._registered_methods_args.items()}
            }

        if method not in self._registered_methods:
            return RPCImplementationError(f"method '{method}' not registered"), None

        try:
            return None, self._registered_methods[method](*params.args, **params.kwargs)
        except Exception as e:
            return RPCExecutionError(e), None


class RPCOverRedisClient(RPCOverRedis, metaclass=ABCMeta):
    _waiting_requests: dict[str, tuple[threading.Lock, RPCResponceMessage | None]]
    _skip_validate_schema: bool
    _strict_validate_schema: bool

    def __init__(
            self,
            conn_url: str,
            service: str,
            skip_validate_schema: bool = False,
            strict_validate_schema: bool = False,
            **kwargs) -> None:
        super().__init__(conn_url, service, **kwargs)
        self._waiting_requests = {}
        self._subscribe_redis()
        self._skip_validate_schema = skip_validate_schema
        self._strict_validate_schema = strict_validate_schema

        self._rpc_reassign_methods()

    def _subscribe_redis(self):
        channel = self._rds.pubsub()
        channel.subscribe(f'{self._key_prefix}/responce/{self._instance_guid}')
        self.logger.debug(f'subscribe {self._key_prefix}/responce/{self._instance_guid}')

        def handle_messagees():
            while self._running:
                message: dict | None = channel.get_message(ignore_subscribe_messages=True, timeout=10)
                if not message: continue
                if not message['data']: continue
                self.logger.debug(f'received {self._key_prefix}/responce/{self._instance_guid} {message["data"]}')
                self._on_event(RPCResponceMessage.model_validate_json(message['data']))

        thread = threading.Thread(target=handle_messagees, daemon=True)
        thread.start()
        self._running_threads.append(thread)

    def _on_event(self, data: RPCResponceMessage):
        request_guid = data.request.hex

        if request_guid not in self._waiting_requests:
            self.logger.warning(f'received unknown message with guid {request_guid}')
            return

        lock, _ = self._waiting_requests.pop(request_guid)
        self._waiting_requests[request_guid] = (lock, data)
        lock.release()

    def _call_rpc(self, method: str, args: list, kwargs: dict) -> dict:
        request_uuid = uuid.uuid4().hex
        request_lock = threading.Lock()

        self._waiting_requests[request_uuid] = (request_lock, None)
        request_lock.acquire()

        payload = {
            'protocol': self._protocol_version,
            'method': method,
            'params': {
                'args': args,
                'kwargs': kwargs,
            },
            'request': request_uuid,
            'client': self._instance_guid,
        }
        payload = json.dumps(payload)

        self._rds.xadd(f'{self._key_prefix}/request/{self._service}', {'data': payload})
        self.logger.debug(f'xadd {self._key_prefix}/request/{self._service} {payload}')
        # ...
        # ...
        # wait answer
        # ...
        # ...
        lock_success = request_lock.acquire(timeout=math.ceil(self._remote_exec_timeout / 1000))
        lock, responce = self._waiting_requests.pop(request_uuid)

        if lock_success:
            if responce.error:
                _class = globals()[responce.error['type']]
                raise _class(
                    responce.error['parent_exception'] if responce.error['parent_exception'] else responce['message']
                )

            return responce.result

        raise RPCTimeoutError()

    def _rpc_reassign_methods(self):
        methods = {x: y for x, y in self.__class__.__dict__.items() if
                   type(y) is FunctionType and not x.startswith('_')}

        if not self._skip_validate_schema:
            try:
                service_schema_validation_options: dict = self._call_rpc('_rpc_schema_', [], {})
                service_schema: dict[str, dict[str, str]] = service_schema_validation_options['types']
                force_strict_validate_schema: bool = service_schema_validation_options['force_strict_validate_schema']
            except RPCTimeoutError:
                self._skip_validate_schema = True
                self.logger.warning('cannot get schema from service, skipping validation')

        def verify_type_hinting_err(err: str) -> None:
            if self._strict_validate_schema or force_strict_validate_schema:
                if force_strict_validate_schema:
                    self.logger.warning('remote force_strict_validate_schema is true, ignoring self._strict_validate_schema')
                raise RPCTypesMismatch(err)
            else:
                self.logger.warning(err)

        def verify_type_hinting(m_name: str, annotations: dict[str, type]) -> None:
            s_annotations = service_schema.get(m_name)
            err = verify_type_hinting_err

            if s_annotations is None:
                return err(f"local declared '{m_name}' does not exist on remote {self._service}")

            i_annotations = {k: (f'{v.__module__}/{v.__name__}' if v is not None else 'builtins/NoneType') for k, v in annotations.items()}

            if sorted(i_annotations.keys()) != sorted(s_annotations.keys()):
                return err(f"method '{m_name}' arguments mismatch (local {i_annotations} vs remote {s_annotations})")

            for arg_name, arg_type in s_annotations.items():
                if i_annotations[arg_name] != arg_type:
                    return err(f"method {m_name} arg '{arg_name}' type mismatch (local {i_annotations[arg_name]} vs remote {arg_type})")

        # noinspection PyUnusedLocal
        def m_modificator(m_name: str, annotations: dict[str, type], default_values: dict[str, Any]) -> Callable:

            def replaced_f(*args, **kwargs):
                pre_f = methods.get(f'_{m_name}_pre')
                post_f = methods.get(f'_{m_name}_post')

                # TODO: fill default values if not exists

                args = list(args)
                args, kwargs = pre_f(self, *args, **kwargs) if pre_f else (args, kwargs)

                resp = self._call_rpc(m_name, args, kwargs)

                resp = post_f(resp) if post_f else resp
                return resp

            return replaced_f

        for name, handler in methods.items():
            _default_values = dict(zip(handler.__code__.co_varnames[-len(handler.__defaults__):], handler.__defaults__)) \
                if handler.__defaults__ else {}

            self.logger.info(f"replacing method '{name}' {handler.__annotations__}")
            if not self._skip_validate_schema: verify_type_hinting(name, handler.__annotations__)
            setattr(self, name, m_modificator(name, handler.__annotations__, _default_values))
