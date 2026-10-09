"""Render entry point; no interactive terminal is required."""
import os, re
from altivia.db import init_db, db, bootstrap_admin
from altivia.server import serve

def main():
    if os.environ.get('ALTIVIA_COOKIE_SECURE') != '1':
        raise RuntimeError('ALTIVIA_COOKIE_SECURE=1 requerido para despliegue público HTTPS')
    if not os.environ.get('ALTIVIA_DATA_DIR'):
        raise RuntimeError('Configure ALTIVIA_DATA_DIR con almacenamiento persistente')
    init_db()
    with db() as conn:
        exists = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if not exists:
        username=os.environ.get('ALTIVIA_ADMIN_USER','').strip().lower()
        password=os.environ.get('ALTIVIA_ADMIN_PASSWORD','')
        fullname=os.environ.get('ALTIVIA_ADMIN_NAME','Administrador ALTIVIA').strip()
        if not re.fullmatch(r'[a-z0-9._-]{3,40}',username) or len(password)<12 or not fullname:
            raise RuntimeError('Primera instalación: configure ALTIVIA_ADMIN_USER y ALTIVIA_ADMIN_PASSWORD (mínimo 12 caracteres) como variables secretas en Render.')
        bootstrap_admin(username,fullname,password)
        print('Administrador inicial creado. Elimine la variable ALTIVIA_ADMIN_PASSWORD en Render tras iniciar sesión.',flush=True)
    port=int(os.environ.get('PORT','10000'))
    if not 1<=port<=65535:raise ValueError('Puerto inválido')
    serve('0.0.0.0',port)
if __name__=='__main__':main()
