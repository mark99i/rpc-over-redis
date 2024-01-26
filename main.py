from rpc_over_redis import RPCOverRedis

r = RPCOverRedis('', 'i')

@r.register
def testing(data: dict) -> dict:
    print(f'testing: {data['sd']}')
    return {'i': data['sd'] + 2}

print(r.call('testing', {'sd': 1}))
# testing: 1
# {'i': 3}