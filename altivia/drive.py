"""Google Drive REST OAuth with server-held refresh token; uses Python standard library only."""
import json,os,urllib.request,urllib.parse,urllib.error,secrets,time,mimetypes
from pathlib import Path
from .db import DATA

TOKEN_PATH=DATA / 'google_tokens.json'
CLIENT_PATH=DATA / 'google_oauth_client.json'
SCOPE='https://www.googleapis.com/auth/drive'
ROOT_ID=os.getenv('GOOGLE_DRIVE_ROOT_ID','1rOoOcJ9SXHHc9BX6tLHjDIfE2_SqkeA1')

def client():
    if not CLIENT_PATH.exists():raise RuntimeError('Falta data/google_oauth_client.json (credencial OAuth de Google Cloud).')
    config=json.loads(CLIENT_PATH.read_text(encoding='utf-8'))
    return config.get('web') or config.get('installed') or {}

def redirect_uri():return os.getenv('GOOGLE_REDIRECT_URI','http://localhost:8765/drive/callback')

def authorization_url(state):
    c=client()
    if not c.get('client_id'):raise RuntimeError('El archivo OAuth no tiene client_id.')
    q={'client_id':c['client_id'],'redirect_uri':redirect_uri(),'response_type':'code','scope':SCOPE,
       'access_type':'offline','prompt':'consent','state':state,'include_granted_scopes':'true'}
    return 'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(q)

def _jsonrequest(url, data=None, method=None, headers=None):
    if isinstance(data,dict):data=json.dumps(data).encode()
    h={'User-Agent':'ALTIVIA-Facturas/1.0'}
    if headers:h.update(headers)
    request=urllib.request.Request(url,data=data,headers=h,method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(request,timeout=25) as r:
            b=r.read(); return json.loads(b) if b else {}
    except urllib.error.HTTPError as exc:
        body=exc.read()[:400].decode(errors='replace')
        raise RuntimeError(f'Google API HTTP {exc.code}: {body}') from exc

def _save_token(value):
    TOKEN_PATH.write_text(json.dumps(value),encoding='utf-8')
    try:os.chmod(TOKEN_PATH,0o600)
    except OSError:pass

def exchange_code(code):
    c=client(); payload={'code':code,'client_id':c['client_id'],'client_secret':c['client_secret'],
                           'redirect_uri':redirect_uri(),'grant_type':'authorization_code'}
    data=urllib.parse.urlencode(payload).encode()
    tok=_jsonrequest('https://oauth2.googleapis.com/token',data,headers={'Content-Type':'application/x-www-form-urlencoded'})
    if not tok.get('refresh_token'):raise RuntimeError('Google no entregó refresh_token. Reautoriza con prompt=consent.')
    tok['expires_at']=time.time()+tok.get('expires_in',3600)-90
    _save_token(tok)
    return True

def access_token():
    if not TOKEN_PATH.exists():raise RuntimeError('Google Drive sin conectar. Autoriza desde Ajustes de Drive.')
    tok=json.loads(TOKEN_PATH.read_text(encoding='utf-8'))
    if tok.get('expires_at',0)>time.time()+30:return tok['access_token']
    c=client();data=urllib.parse.urlencode({'client_id':c['client_id'],'client_secret':c['client_secret'],
       'refresh_token':tok['refresh_token'],'grant_type':'refresh_token'}).encode()
    new=_jsonrequest('https://oauth2.googleapis.com/token',data,headers={'Content-Type':'application/x-www-form-urlencoded'})
    tok.update(new);tok['expires_at']=time.time()+new.get('expires_in',3600)-90
    _save_token(tok);return tok['access_token']

def api(url,data=None,method=None,headers=None):
    h={'Authorization':'Bearer '+access_token()};h.update(headers or {})
    if isinstance(data,dict):h['Content-Type']='application/json; charset=UTF-8'
    return _jsonrequest(url,data,method,h)

def _escape_q(s):return s.replace('\\','\\\\').replace("'","\\'")

def folder(name,parent):
    q=f"name = '{_escape_q(name)}' and mimeType = 'application/vnd.google-apps.folder' and '{_escape_q(parent)}' in parents and trashed = false"
    args=urllib.parse.urlencode({'q':q,'fields':'files(id,name),nextPageToken','pageSize':100})
    found=api('https://www.googleapis.com/drive/v3/files?'+args).get('files',[])
    if found:return found[0]['id']
    created=api('https://www.googleapis.com/drive/v3/files?fields=id',
                {'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]})
    return created['id']

def upload(path,filename,mime,parent):
    boundary='altivia'+secrets.token_hex(12)
    metadata=json.dumps({'name':filename,'parents':[parent]},ensure_ascii=False).encode()
    content=Path(path).read_bytes()
    payload=(b'--'+boundary.encode()+b'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+metadata+b'\r\n'
        +b'--'+boundary.encode()+b'\r\nContent-Type: '+mime.encode()+b'\r\n\r\n'+content+b'\r\n'
        +b'--'+boundary.encode()+b'--\r\n')
    result=api('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name',
               payload,headers={'Content-Type':'multipart/related; boundary='+boundary})
    return result['id']

def sync_invoice(c,row):
    if row['drive_file_id']:return row['drive_file_id']
    user=c.execute('SELECT full_name,folder_key FROM users WHERE id=?',(row['owner_id'],)).fetchone()
    label=''.join(ch if ch.isalnum() or ch in ' _-' else '_' for ch in user['full_name']).strip()[:54]
    parent=folder(f'{label}_{user["folder_key"]}',ROOT_ID)
    date_folder=folder(row['issued_on'][8:10]+'-'+row['issued_on'][5:7]+'-'+row['issued_on'][:4],parent)
    return upload(row['local_path'],row['original_filename'],row['mime_type'],date_folder)
