#!/usr/bin/env python3
"""Explicit operator action; never invoked by Helm. No application credentials."""
import argparse
import getpass
import json
import subprocess
import time


KEY = 'dot-control:state'


def transition(client, action, epoch, configs_epoch=None):
    """Redis >=8.4 CAS. Never retry an ambiguous write or decrement epoch."""
    if type(epoch) is not int or epoch < 1:
        raise RuntimeError('positive integer epoch required')
    old = client.get(KEY)
    if action == 'initialize':
        if old is not None:
            raise RuntimeError('already initialized; will not overwrite')
        state = {'enabled': False, 'epoch': epoch}
        result = client.set(KEY, json.dumps(state), nx=True)
    else:
        try:
            state = json.loads(old)
        except (TypeError, ValueError):
            raise RuntimeError('missing or malformed control state') from None
        if (not isinstance(state, dict) or set(state) != {'enabled', 'epoch'}
                or type(state['enabled']) is not bool or type(state['epoch']) is not int
                or state['epoch'] != epoch):
            raise RuntimeError('invalid state or epoch mismatch; stopped')
        if action == 'security-stop':
            state = {'enabled': False, 'epoch': epoch + 1}
        elif action == 'maintenance-pause':
            state = {'enabled': False, 'epoch': epoch}
        elif action == 'enable':
            if configs_epoch != epoch or state['enabled']:
                raise RuntimeError('disabled state and verified matching deployment epoch required')
            state = {'enabled': True, 'epoch': epoch}
        else:
            raise RuntimeError('unsupported action')
        # Redis 8.4 SET IFEQ performs atomic compare-and-set with GET/SET ACL only.
        result = client.execute_command('SET', KEY, json.dumps(state), 'IFEQ', old)
    if result not in (True, 'OK', b'OK'):
        raise RuntimeError('state changed concurrently; no retry; inspect state')
    # Only constrained non-secret state is returned, never raw Redis content.
    return state


def main():
    import redis
    from redis.retry import Retry
    from redis.backoff import NoBackoff
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['initialize', 'enable', 'security-stop', 'maintenance-pause'])
    p.add_argument('--epoch', type=int, required=True)
    p.add_argument('--verified-configs-epoch', type=int, help='Enable only: operator attestation that both deployed service epochs were verified')
    p.add_argument('--port', type=int, default=16379)
    a = p.parse_args()
    if a.epoch < 1 or not 1024 <= a.port <= 65535:
        p.error('positive epoch and unprivileged local port required')
    password = getpass.getpass('Dedicated Redis operator password (not saved): ')
    # Choose an unused local port; any pre-existing listener causes forwarding failure.
    import socket
    with socket.socket() as s:
        s.bind(('127.0.0.1', a.port))
    proc = subprocess.Popen(['kubectl', '--context', 'kkamji-lab', '-n', 'hindsight-dot',
        'port-forward', '--address=127.0.0.1', 'state-0', f'{a.port}:6379'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        c = redis.Redis(host='127.0.0.1', port=a.port, username='operator', password=password,
                        socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
                        retry=Retry(NoBackoff(), 0))
        deadline = time.monotonic() + 15
        while True:
            if proc.poll() is not None:
                raise RuntimeError('port-forward exited; no action permitted')
            try:
                old = c.get('dot-control:state')
                break
            except redis.exceptions.ConnectionError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('bounded port-forward readiness deadline exceeded')
                time.sleep(.2)
        state = transition(c, a.action, a.epoch, a.verified_configs_epoch)
        print(json.dumps(state))
        c.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

if __name__ == '__main__':
    main()
