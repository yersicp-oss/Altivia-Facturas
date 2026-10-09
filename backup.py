"""Coherent SQLite backup + local evidence documents; excludes OAuth/API secrets."""
from altivia.db import DATA,DBFILE,db,init_db
from datetime import datetime
import sqlite3,os,zipfile,tempfile
from pathlib import Path

def main():
    init_db()
    backupdir=DATA.parent/'respaldos';backupdir.mkdir(exist_ok=True)
    name='ALTIVIA_Respaldo_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip'
    dest=backupdir/name
    with tempfile.TemporaryDirectory() as temp:
        scratch=Path(temp)/'altivia.sqlite3'
        src=sqlite3.connect(DBFILE)
        try:
            destdb=sqlite3.connect(scratch)
            try:src.backup(destdb)
            finally:destdb.close()
        finally:src.close()
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.write(scratch,'altivia.sqlite3')
            for folder in ('uploads','archive'):
                d=DATA/folder
                if d.exists():
                    for f in d.rglob('*'):
                        if f.is_file():z.write(f, f.relative_to(DATA))
    print('\nRespaldo generado:',dest)
    print('Este archivo contiene comprobantes y datos confidenciales. Guárdalo en un lugar seguro.')
if __name__=='__main__':main()
