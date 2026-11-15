#!/usr/bin/env python3
"""Render disposable synthetic-only Cilium acceptance Jobs; does not apply anything."""
import argparse
import ipaddress
import json
import re


def render(image, native_ip, public_ip):
    if not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image):
        raise ValueError('digest-pinned service image required')
    for ip in [native_ip, public_ip]:
        ipaddress.ip_address(ip)
    checks = {
        'proxy': [('backend-policy.hindsight-dot.svc.cluster.local.', 8001, True),
                  ('state.hindsight-dot.svc.cluster.local.', 6379, True),
                  ('synthetic-backend.hindsight-dot.svc.cluster.local.', 8080, False),
                  (native_ip, 8888, False), (public_ip, 443, False)],
        'gateway': [('synthetic-backend.hindsight-dot.svc.cluster.local.', 8080, True),
                    ('state.hindsight-dot.svc.cluster.local.', 6379, True),
                    (native_ip, 8888, False)],
        'outsider': [('backend-policy.hindsight-dot.svc.cluster.local.', 8001, False),
                     ('state.hindsight-dot.svc.cluster.local.', 6379, False),
                     ('synthetic-backend.hindsight-dot.svc.cluster.local.', 8080, False)]}
    objects = []
    for role, cases in checks.items():
        code = 'import socket,sys,json\nfailed=False\n'
        code += 'for host,port,wanted in ' + repr(cases) + ':\n'
        code += ' try:\n  s=socket.create_connection((host,port),3);s.close();ok=True\n except socket.gaierror:\n  print("DNS FAILURE",host);failed=True;continue\n except OSError:\n  ok=False\n print(json.dumps({"host":host,"port":port,"connected":ok,"expected":wanted}));failed|=(ok!=wanted)\nsys.exit(int(failed))\n'
        objects.append({'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {
            'name': 'dot-network-' + role, 'namespace': 'hindsight-dot'}, 'spec': {
            'backoffLimit': 0, 'activeDeadlineSeconds': 90, 'ttlSecondsAfterFinished': 600,
            'template': {'metadata': {'labels': {'app': 'hindsight-dot', 'component': role,
                'dot-acceptance': 'true'}}, 'spec': {'automountServiceAccountToken': False,
                'restartPolicy': 'Never', 'securityContext': {'runAsNonRoot': True,
                'runAsUser': 10001, 'runAsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'probe', 'image': image, 'command': ['python', '-c', code],
                # Always unready, so service selectors never add probe to ready endpoints.
                'readinessProbe': {'httpGet': {'path': '/', 'port': 65534}, 'periodSeconds': 1},
                'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                    'capabilities': {'drop': ['ALL']}},
                'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'},
                              'limits': {'cpu': '100m', 'memory': '64Mi'}}}]}}}})
    return {'apiVersion': 'v1', 'kind': 'List', 'items': objects}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True)
    p.add_argument('--native-ip', required=True)
    p.add_argument('--public-native-ip', required=True)
    a = p.parse_args()
    print(json.dumps(render(a.image, a.native_ip, a.public_native_ip), indent=2))
