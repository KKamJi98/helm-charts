import contextlib,io,json,os,stat,tempfile,unittest
from pathlib import Path
from urllib.parse import urlsplit
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'/'hindsight-dot'))
from prepare_staging_secrets import prepare,main,BundleError,CALLBACK,PROJECT

class BundleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
  self.google=self.root/'fixture.json'
  self.google.write_text(json.dumps({'web':{'project_id':PROJECT,'client_id':'synthetic.apps.googleusercontent.com','client_secret':'synthetic-only-client-secret','redirect_uris':[CALLBACK]}}));self.google.chmod(0o600)
 def tearDown(self):self.tmp.cleanup()
 def test_private_split_no_stdout_or_operator_in_runtime(self):
  out=self.root/'new';buf=io.StringIO()
  with contextlib.redirect_stdout(buf):self.assertEqual(main(['--google-client',str(self.google),'--output-dir',str(out),'--epoch','1']),0)
  r=json.loads((out/'ssm-runtime.json').read_text());op=json.loads((out/'operator-local.json').read_text())
  self.assertEqual(set(r),{'oauth_redis_url','gate_redis_url','storage_key','signing_key','google_client_secret','redis_acl'})
  self.assertNotIn(urlsplit(op['redis_url']).password,json.dumps(r))
  self.assertNotIn(r['google_client_secret'],buf.getvalue());self.assertNotIn(r['storage_key'],buf.getvalue())
  self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o700)
  for f in out.iterdir():self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
  self.assertFalse(op['initial_state']['enabled']);self.assertNotIn('+@all',r['redis_acl'])
  self.assertIn('~dot-oauth-e1:*',r['redis_acl'])
 def test_no_overwrite(self):
  out=self.root/'new';prepare(self.google,out,1);old=(out/'ssm-runtime.json').read_bytes()
  with self.assertRaises(FileExistsError):prepare(self.google,out,1)
  self.assertEqual((out/'ssm-runtime.json').read_bytes(),old)
 def test_insecure_input_denied(self):
  self.google.chmod(0o644)
  with self.assertRaises(BundleError):prepare(self.google,self.root/'new',1)
  self.assertFalse((self.root/'new').exists())
 def test_symlink_denied(self):
  link=self.root/'link';link.symlink_to(self.google)
  with self.assertRaises(BundleError):prepare(link,self.root/'new',1)
 def test_wrong_project_denied(self):
  d=json.loads(self.google.read_text());d['web']['project_id']='wrong';self.google.write_text(json.dumps(d))
  with self.assertRaises(BundleError):prepare(self.google,self.root/'new',1)
 def test_insecure_parent_denied(self):
  self.root.chmod(0o755)
  with self.assertRaises(BundleError):prepare(self.google,self.root/'new',1)

 def test_bound_owner_epoch3_counter_acl(self):
  owner=self.root/'owner.json';owner.write_text(json.dumps({'sub':'fixture-owner','email':'rlaxowl5460@gmail.com','tools_denied':True}));owner.chmod(0o600)
  out=self.root/'e3';prepare(self.google,out,3,owner)
  runtime=json.loads((out/'ssm-runtime.json').read_text())
  self.assertEqual(runtime['owner_sub'],'fixture-owner')
  rate=next(x for x in runtime['redis_acl'].splitlines() if x.startswith('user rate '))
  self.assertIn('~dot-dcr-e3:state',rate);self.assertIn('+set',rate);self.assertNotIn('+eval',rate);self.assertNotIn('dot-control',rate)
  self.assertIn('%RW~dot-dcr-e3:state',runtime['redis_acl'])
