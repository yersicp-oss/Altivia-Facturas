import sqlite3, os, secrets, hashlib, hmac
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('ALTIVIA_DATA_DIR', str(BASE / 'data')))
DBFILE = DATA / 'altivia.sqlite3'
DATA.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def db():
    conn=sqlite3.connect(DBFILE,timeout=20)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    return conn

def init_db():
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','miembro','contador')),
          active INTEGER NOT NULL DEFAULT 1, folder_key TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL,
          expires_at TEXT NOT NULL, oauth_state TEXT, oauth_started TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invoices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_id INTEGER NOT NULL REFERENCES users(id), project_id INTEGER REFERENCES projects(id),
          receipt_type TEXT NOT NULL DEFAULT 'Factura', series TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '',
          issued_on TEXT NOT NULL, due_on TEXT, provider TEXT NOT NULL, ruc TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '', subtotal REAL NOT NULL DEFAULT 0, igv REAL NOT NULL DEFAULT 0,
          total REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'PEN', terms TEXT NOT NULL DEFAULT '',
          review_status TEXT NOT NULL DEFAULT 'Pendiente', review_notes TEXT NOT NULL DEFAULT '',
          deleted_at TEXT, duplicate_sequence INTEGER NOT NULL DEFAULT 0,
          local_path TEXT NOT NULL, original_filename TEXT NOT NULL, mime_type TEXT NOT NULL,
          drive_file_id TEXT, drive_status TEXT NOT NULL DEFAULT 'Pendiente',
          extraction_method TEXT, extraction_confidence TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS invoice_duplicate_guard ON invoices(ruc,receipt_type,series,number,duplicate_sequence)
          WHERE deleted_at IS NULL AND ruc<>'' AND series<>'' AND number<>'';
        CREATE INDEX IF NOT EXISTS idx_invoices_owner ON invoices(owner_id);
        CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(issued_on);
        CREATE TABLE IF NOT EXISTS payments (
          id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
          amount REAL NOT NULL CHECK(amount>0), currency TEXT NOT NULL, paid_on TEXT NOT NULL,
          method TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS uploads_pending (
          token TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), path TEXT NOT NULL,
          filename TEXT NOT NULL, mime_type TEXT NOT NULL, extracted_json TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), event TEXT NOT NULL,
          subject_type TEXT, subject_id INTEGER, details TEXT NOT NULL DEFAULT '', ip TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS public_attempts (
          id INTEGER PRIMARY KEY, ip TEXT NOT NULL, stage TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_public_attempts ON public_attempts(ip,stage,created_at);
        CREATE TABLE IF NOT EXISTS login_attempts (
          id INTEGER PRIMARY KEY, username TEXT, ip TEXT NOT NULL, success INTEGER NOT NULL, attempted_at TEXT NOT NULL
        );
        ''')

def hash_password(password):
    if len(password) < 10: raise ValueError('La contraseña debe tener por lo menos 10 caracteres.')
    salt=secrets.token_bytes(16)
    val=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return f'scrypt$16384$8$1${salt.hex()}${val.hex()}'

def verify_password(pw, stored):
    try:
        _,n,r,p,salt,expected=stored.split('$')
        val=hashlib.scrypt(pw.encode(),salt=bytes.fromhex(salt),n=int(n),r=int(r),p=int(p),dklen=32)
        return hmac.compare_digest(val,bytes.fromhex(expected))
    except (ValueError,TypeError): return False

def audit(conn, actor, event, subject_type='', subject_id=None, details='', ip=''):
    conn.execute('INSERT INTO audit(actor_id,event,subject_type,subject_id,details,ip,created_at) VALUES(?,?,?,?,?,?,?)',
                 (actor,event,subject_type,subject_id,str(details)[:1200],ip,now()))

def bootstrap_admin(username, fullname, password):
    init_db()
    with db() as c:
        if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]: return False
        cur=c.execute('INSERT INTO users(username,full_name,password_hash,role,folder_key,created_at) VALUES(?,?,?,?,?,?)',
                  (username.strip().lower(),fullname.strip(),hash_password(password),'admin',secrets.token_hex(5),now()))
        audit(c,cur.lastrowid,'ADMIN_INICIALIZADO','user',cur.lastrowid)
        return True

def paid_total(c, invoice_id):
    return round(c.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice_id=?',(invoice_id,)).fetchone()[0],2)

def payment_status(total,paid):
    return 'Pagada' if paid >= total-0.005 and total > 0 else ('Pago parcial' if paid > 0 else 'Pendiente de pago')
