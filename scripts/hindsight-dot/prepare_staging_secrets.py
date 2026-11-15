#!/usr/bin/env python3
"""Local-only secret bundle. No network/AWS/native-key reads. Never prints secrets.

Input Google client is read only on explicit execution, never at import. The
output directory must not exist; existing bundles are never replaced/rotated.
Runtime JSON is for a dedicated SSM SecureString, not automatic upload.
"""
import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import stat
import sys
from urllib.parse import quote

GOOGLE_DEFAULT=Path.home()/'.local/share/hindsight-dot-private/google-client.json'
REDIS_HOST='state.hindsight-dot.svc.cluster.local'
CALLBACK='https://hindsight-dot.kkamji.net/auth/callback'
PROJECT='favorable-array-514714-s0'

class BundleError(Exception):pass

def reject_symlink_components(path):
    absolute=path.absolute()
    for part in [*reversed(absolute.parents),absolute]:
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode):raise BundleError('Symlink path refused')

def read_google(path):
    reject_symlink_components(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077 or info.st_size>32768:
            raise BundleError('Google client file must be owner-only regular file')
        data=json.load(f)
    web=data.get('web') if isinstance(data,dict) else None
    if not isinstance(web,dict):raise BundleError('Expected Google Web OAuth client JSON')
    if web.get('project_id')!=PROJECT:raise BundleError('Unexpected OAuth project')
    if CALLBACK not in web.get('redirect_uris',[]):raise BundleError('Expected callback is missing')
    cid=web.get('client_id');secret=web.get('client_secret')
    if not isinstance(cid,str) or not cid.endswith('.apps.googleusercontent.com') or len(cid)>512:raise BundleError('Invalid client ID')
    if not isinstance(secret,str) or not 12<=len(secret)<=2048 or any(x.isspace() for x in secret):raise BundleError('Invalid client secret')
    return cid,secret

def write_new_json(directory,name,value):
    path=directory/name
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(value,f,ensure_ascii=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def prepare(google_path,output_dir,epoch,owner_path=None):
    owner=None
    if owner_path is not None:
        owner_path=Path(owner_path);reject_symlink_components(owner_path)
        fd=os.open(owner_path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077 or st.st_size>2048:raise BundleError('Owner file permissions')
            owner=json.load(f)
        if not isinstance(owner,dict) or owner.get('email')!='rlaxowl5460@gmail.com' or owner.get('tools_denied') is not True or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',str(owner.get('sub',''))):raise BundleError('Verified owner required')

    if type(epoch) is not int or not 1<=epoch<=1000000:raise BundleError('Invalid epoch')
    google_path=Path(google_path);output_dir=Path(output_dir)
    reject_symlink_components(output_dir)
    parent=output_dir.parent
    info=parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise BundleError('Output parent must exist, owned by you, mode0700')
    # Read/validate before creating any output; no partial bundle on invalid input.
    cid,google_secret=read_google(google_path)
    password={role:secrets.token_urlsafe(48) for role in (('oauth','gate','operator','rate') if owner else ('oauth','gate','operator'))}
    hashed={role:hashlib.sha256(value.encode()).hexdigest() for role,value in password.items()}
    acl='\n'.join([
        'user default off',
        f'user oauth on #{hashed["oauth"]} ~dot-oauth-e{epoch}:* +get +set +setex +del +mget +mset +ping +client|setinfo',
        f'user gate on #{hashed["gate"]} %R~dot-control:state +get +ping +client|setinfo',
        f'user operator on #{hashed["operator"]} %RW~dot-control:state +get +set +ping +client|setinfo',
        '',
    ])
    url=lambda role:f'redis://{role}:{quote(password[role],safe="")}@{REDIS_HOST}:6379/0'
    runtime={
        'oauth_redis_url':url('oauth'),'gate_redis_url':url('gate'),
        'storage_key':base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'signing_key':secrets.token_urlsafe(64),
        'google_client_secret':google_secret,'redis_acl':acl,
    }
    if owner:
        runtime['owner_sub']=owner['sub']
        runtime['rate_redis_url']=url('rate')
        runtime['redis_acl']=acl.replace(f'%RW~dot-control:state',f'%RW~dot-control:state %RW~dot-dcr-e{epoch}:state')+f'user rate on #{hashed["rate"]} ~dot-dcr-e{epoch}:state +get +set +time +ttl +ping +client|setinfo\n'
    # Operator plaintext never enters runtime JSON/SSM or service pod mounts.
    operator={
        'redis_url':url('operator'),'state_key':'dot-control:state',
        'initial_state':{'enabled':False,'epoch':epoch},
        'instructions':'Operator-only local file. Not runtime SSM. No automatic SET or upload performed.',
    }
    manifest={
        'schema':1,'epoch':epoch,'google_project':PROJECT,'google_client_id':cid,
        'google_callback':CALLBACK,'redis_host':REDIS_HOST,
        'runtime_ssm_parameter':'/kkamji/automation/hindsight/dot',
        'ssm_type_required':'SecureString','aws_writes_performed':False,
        'native_credentials_included':False,'operator_in_runtime':False,
        'runtime_json_bytes':len(json.dumps(runtime,separators=(',',':')).encode()),
    }
    # Never replace an existing bundle, including partially-created output.
    os.mkdir(output_dir,0o700)
    write_new_json(output_dir,'ssm-runtime.json',runtime)
    write_new_json(output_dir,'operator-local.json',operator)
    write_new_json(output_dir,'manifest.json',manifest)
    directory_fd=os.open(output_dir,os.O_RDONLY)
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
    return manifest

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--google-client',type=Path,default=GOOGLE_DEFAULT)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--epoch',type=int,required=True)
    parser.add_argument('--verified-owner',type=Path)
    args=parser.parse_args(argv)
    os.umask(0o077)
    try:prepare(args.google_client,args.output_dir,args.epoch,args.verified_owner)
    except Exception:
        print('Secret bundle not completed. Check private input permissions, project/callback and unused output directory. No AWS writes were attempted.',file=sys.stderr)
        return 1
    print('Local staging bundle created. No secrets printed. No AWS writes performed.')
    return 0
if __name__=='__main__':raise SystemExit(main())
