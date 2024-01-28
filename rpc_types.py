from urllib.parse import ParseResult, urlparse
from uuid import UUID

import pydantic


class RPCResponceMessageErrorParentExc(pydantic.BaseModel):
    type: str
    message: list | None


class RPCResponceMessageError(pydantic.BaseModel):
    type: str
    message: str
    parent_exception: RPCResponceMessageErrorParentExc | None = None
    arg: list


class RPCResponceMessage(pydantic.BaseModel):
    protocol: int = 1
    request: UUID
    result: str | dict | bool | int | list | None = None
    error: dict | None = None


class RPCRequestMessageParams(pydantic.BaseModel):
    args: list
    kwargs: dict


class RPCRequestMessage(pydantic.BaseModel):
    protocol: int = 1
    method: str
    params: RPCRequestMessageParams
    request: str
    client: str


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


class RPCError(RuntimeError):
    def dict(self):
        arg = self.args[0] if len(self.args) > 0 else None
        return {
            'type': self.__class__.__name__,
            'message': str(self),
            'parent_exception': {
                'type': arg.__class__.__name__,
                'message': arg.args
            } if isinstance(arg, Exception | TimeoutError | RuntimeError) else None,
            'arg': [str(_) for _ in self.args],
        }


class RPCExecutionError(RPCError):
    ...


class RPCImplementationError(RPCError):
    ...


class RPCTypesMismatch(RPCError):
    ...


class RPCTimeoutError(RPCError, TimeoutError):
    ...
