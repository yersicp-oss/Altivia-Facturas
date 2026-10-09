"""Windows launcher. Works with Python standard library; OCR libraries are optional."""
from altivia.db import init_db,db,bootstrap_admin,hash_password,audit,now
from altivia.server import serve
import os,sys,getpass,re,threading,webbrowser,time

def read_password(label):
    while True:
        p=getpass.getpass(label)
        if len(p)<10:print('Usa por lo menos 10 caracteres.');continue
        if p!=getpass.getpass('Confirma la contraseña: '):print('Las contraseñas no coinciden.');continue
        return p

def main():
    init_db()
    reset='--reset-admin' in sys.argv
    if reset:
        with db() as c:
            existing=c.execute("SELECT id,username FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
            if not existing:print('No hay administradores activos.');return
            print('RECUPERACIÓN LOCAL: administra este servidor solamente desde un equipo de confianza.')
            print('Se actualizará la clave del administrador:',existing['username'])
            if input('Escribe CONFIRMAR para continuar: ').strip()!='CONFIRMAR':return
            pw=read_password('Nueva contraseña: ')
            c.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(pw),existing['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(existing['id'],))
            audit(c,existing['id'],'RECUPERACION_LOCAL_CLAVE','user',existing['id']);c.commit()
            print('Clave restablecida. Reinicia la aplicación.');return
    with db() as c:
        existing=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if not existing:
        print('\n'+'='*60+'\n ALTIVIA · CONFIGURACIÓN DEL PRIMER ADMINISTRADOR\n'+'='*60)
        while True:
            username=input('Usuario administrador (ej.: admin.altivia): ').strip().lower()
            if re.fullmatch('[a-z0-9._-]{3,40}',username):break
            print('Usuario inválido: usa entre 3 y 40 letras, números, punto, guión o _.')
        full_name=input('Nombre completo: ').strip()
        if not full_name:full_name='Administrador ALTIVIA'
        pw=read_password('Contraseña maestra (mínimo 10 caracteres): ')
        bootstrap_admin(username,full_name,pw)
        print('Administrador inicial creado correctamente.\n')
    host=os.getenv('ALTIVIA_HOST','127.0.0.1');port=int(os.getenv('ALTIVIA_PORT','8765'))
    if '--no-browser' not in sys.argv:
        def open_browser():time.sleep(1.3);webbrowser.open(f'http://localhost:{port}/')
        threading.Thread(target=open_browser,daemon=True).start()
    if host=='0.0.0.0':print('\nAVISO: servidor accesible por red local. NO exponer directamente a Internet sin HTTPS y autenticación perimetral.')
    serve(host,port)
if __name__=='__main__':main()
