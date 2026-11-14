"""Offline render contracts; does not prove live network enforcement."""
import json, pathlib, subprocess, unittest
import yaml
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=['helm','template','hindsight-dot','charts/hindsight-dot','-n','hindsight-dot','-f','charts/hindsight-dot/kkamji_local_values.yaml']
ARGS=['--set','enabled=true','--set','image.repository=example.invalid/dot','--set','image.digest=sha256:'+'a'*64,'--set','owner.sub=synthetic','--set','googleClientId=synthetic','--set','redirectUris[0]=https://client.invalid/callback']
def render(extra=(),enabled=True,ok=True):
 r=subprocess.run(BASE+(ARGS if enabled else [])+list(extra),cwd=ROOT,text=True,capture_output=True)
 if ok and r.returncode:raise AssertionError(r.stderr)
 if not ok:return r.returncode
 return [d for d in yaml.safe_load_all(r.stdout) if d]
def named(docs,kind,name):return next(d for d in docs if d['kind']==kind and d['metadata']['name']==name)
class Chart(unittest.TestCase):
 def test_default_off(self):self.assertEqual(render(enabled=False),[])
 def test_inputs_failclosed(self):
  for args in [('--set','owner.sub='),('--set','image.digest=latest'),('--set','publicRoute.enabled=true'),('--set','syntheticBackend=false'),('--set','capabilities[0]=admin')]:
   self.assertNotEqual(render(args,ok=False),0)
 def test_synthetic_no_native_no_public(self):
  ds=render(['--set','externalSecrets.enabled=true']);raw=json.dumps(ds)
  self.assertFalse(any(d['kind']=='HTTPRoute' for d in ds));self.assertNotIn('hindsight-dot-native',raw)
  self.assertNotIn('hindsight-from-dot-gateway',raw)
  self.assertFalse(any('dataFrom' in d.get('spec',{}) for d in ds))
 def test_workload_containment(self):
  ds=render()
  for name in ['proxy','backend-policy']:
   d=named(ds,'Deployment',name);pod=d['spec']['template']['spec'];self.assertEqual(d['spec']['replicas'],1)
   self.assertFalse(pod['automountServiceAccountToken']);self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])
   self.assertNotIn('hostNetwork',pod)
  state=named(ds,'StatefulSet','state');self.assertEqual(state['spec']['replicas'],1);self.assertEqual(state['spec']['template']['spec']['securityContext']['runAsGroup'],1000)
 def test_production_native_gateway_only(self):
  ds=render(['--set','syntheticBackend=false','--set','native.approved=true','--set','externalSecrets.enabled=true'])
  for name,expected in [('proxy',False),('backend-policy',True)]:
   p=named(ds,'Deployment',name)['spec']['template']['spec'];self.assertEqual('hindsight-dot-native' in json.dumps(p),expected)
  es=named(ds,'ExternalSecret','hindsight-dot-native');self.assertEqual(es['spec']['data'],[{'secretKey':'api_key','remoteRef':{'key':'/kkamji/automation/hindsight/access','property':'api_key'}}])
  self.assertEqual(es['spec']['target']['creationPolicy'],'Orphan')
  self.assertFalse(any(d['metadata']['name']=='synthetic-backend' for d in ds))
 def test_proxy_network_no_native_or_world(self):
  ds=render(['--set','syntheticBackend=false','--set','native.approved=true']);p=named(ds,'CiliumNetworkPolicy','dot-proxy')['spec']
  self.assertNotIn('8888',json.dumps(p));self.assertNotIn('world',json.dumps(p));self.assertNotIn('toCIDR',json.dumps(p))
  dest=[x['matchLabels'].get('component') for r in p['egress'] for x in r.get('toEndpoints',[])];self.assertIn('gateway',dest);self.assertNotIn('api',dest)
 def test_public_explicit_gated(self):
  ds=render(['--set','publicRoute.enabled=true','--set','publicRoute.networkValidated=true']);r=named(ds,'HTTPRoute','hindsight-dot')
  self.assertEqual(r['spec']['rules'][0]['backendRefs'][0]['name'],'proxy')
  self.assertEqual(r['spec']['hostnames'],['hindsight-dot.kkamji.net'])
if __name__=='__main__':unittest.main()
