import os, time, aiosqlite

DB = os.environ.get("DB_PATH", "data/quickai.db")
BASE_LIMIT = int(os.environ.get("DAILY_LIMIT", 10))
FREE_SIGNALS = int(os.environ.get("FREE_SIGNALS", 10))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, ref_by INTEGER, lang TEXT,
  subscribed INTEGER DEFAULT 0, registered INTEGER DEFAULT 0, deposited INTEGER DEFAULT 0,
  deposit_sum REAL DEFAULT 0, deposit_at INTEGER, created INTEGER, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, pair TEXT, tf TEXT, dir TEXT,
  strength INTEGER, entry REAL, created INTEGER, expires INTEGER, exit_price REAL, result TEXT);
CREATE INDEX IF NOT EXISTS ix_sig_user ON signals(user_id, created);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, amount REAL, invoice_id TEXT,
  status TEXT, created INTEGER, paid_at INTEGER);
"""
FLAGS = {"subscribed", "registered", "deposited", "deposit_sum", "deposit_at"}

async def init():
    d = os.path.dirname(DB)
    if d: os.makedirs(d, exist_ok=True)
    async with aiosqlite.connect(DB) as c:
        await c.executescript(SCHEMA)
        try: await c.execute("ALTER TABLE users ADD COLUMN lang TEXT")
        except Exception: pass
        for col in ("credits INTEGER DEFAULT 0", "pro_until INTEGER DEFAULT 0", "free_given INTEGER DEFAULT 0",
                    "pro_notified INTEGER DEFAULT 0", "pro_exp_sent INTEGER DEFAULT 0"):
            try: await c.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception: pass
        await c.execute("UPDATE users SET credits=COALESCE(credits,0)+?, free_given=1 WHERE deposited=1 AND COALESCE(free_given,0)=0", (FREE_SIGNALS,))
        await c.commit()

async def _one(q, a=()):
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        async with c.execute(q, a) as cur:
            r = await cur.fetchone(); return dict(r) if r else None

async def _all(q, a=()):
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        async with c.execute(q, a) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def _run(q, a=()):
    async with aiosqlite.connect(DB) as c:
        cur = await c.execute(q, a); await c.commit(); return cur.lastrowid, cur.rowcount

async def upsert_user(uid, username, first, ref_by=None):
    now = int(time.time())
    if ref_by == uid: ref_by = None
    await _run("INSERT OR IGNORE INTO users(id,username,first_name,ref_by,created,last_seen) VALUES(?,?,?,?,?,?)",
               (uid, username, first, ref_by, now, now))
    await _run("UPDATE users SET username=?, first_name=?, last_seen=? WHERE id=?", (username, first, now, uid))

async def get_user(uid): return await _one("SELECT * FROM users WHERE id=?", (uid,))
async def set_lang(uid, lang): await _run("UPDATE users SET lang=? WHERE id=?", (lang, uid))
async def get_lang(uid):
    u = await get_user(uid); return (u or {}).get("lang") or "ru"

async def set_flag(uid, **kw):
    for k, v in kw.items():
        assert k in FLAGS
        await _run(f"UPDATE users SET {k}=? WHERE id=?", (v, uid))

async def has_access(uid):
    u = await get_user(uid); return bool(u and u["deposited"])

async def refs(uid):
    r = await _one("SELECT COUNT(*) n, COALESCE(SUM(deposited),0) d FROM users WHERE ref_by=?", (uid,))
    return r["n"], r["d"]

async def limit_for(uid):
    _, d = await refs(uid); return BASE_LIMIT + min(2 * d, 10)

async def signals_today(uid):
    t = int(time.time()); start = t - t % 86400
    r = await _one("SELECT COUNT(*) n FROM signals WHERE user_id=? AND created>=?", (uid, start)); return r["n"]

async def add_signal(uid, pair, tf, d, strength, entry, expires):
    return (await _run("INSERT INTO signals(user_id,pair,tf,dir,strength,entry,created,expires) VALUES(?,?,?,?,?,?,?,?)",
                       (uid, pair, tf, d, strength, entry, int(time.time()), expires)))[0]

async def get_signal(sid): return await _one("SELECT * FROM signals WHERE id=?", (sid,))
async def active_signal(uid):
    return await _one("SELECT * FROM signals WHERE user_id=? AND result IS NULL ORDER BY id DESC LIMIT 1", (uid,))
async def settle_signal(sid, exit_price, res):
    """True, если именно этот вызов закрыл сделку (защита от двойного закрытия)."""
    return (await _run("UPDATE signals SET exit_price=?, result=? WHERE id=? AND result IS NULL", (exit_price, res, sid)))[1] > 0
async def due_signals(now):
    return await _all("SELECT * FROM signals WHERE result IS NULL AND expires<=? AND user_id>0", (now,))

async def history(uid, n=8):
    return await _all("SELECT pair,tf,dir,result,(expires-created) AS dur FROM signals WHERE user_id=? AND result IN('W','L','D') ORDER BY id DESC LIMIT ?", (uid, n))

async def user_stats(uid):
    return await _one("""SELECT COUNT(*) total, COALESCE(SUM(result='W'),0) wins, COALESCE(SUM(result='L'),0) losses
                         FROM signals WHERE user_id=? AND result IN('W','L','D')""", (uid,))

async def loss_streak(uid):
    n = 0
    for r in await _all("SELECT result FROM signals WHERE user_id=? AND result IN('W','L','D') ORDER BY id DESC LIMIT 10", (uid,)):
        if r["result"] == "L": n += 1
        else: break
    return n

async def admin_stats():
    now = int(time.time()); start = now - now % 86400
    u = await _one("""SELECT COUNT(*) total, COALESCE(SUM(subscribed),0) sub, COALESCE(SUM(registered),0) reg,
                      COALESCE(SUM(deposited),0) dep, COALESCE(SUM(created>=?),0) new_today FROM users""", (start,))
    s = await _one("""SELECT COUNT(*) total, COALESCE(SUM(created>=?),0) today, COALESCE(SUM(result='W'),0) w,
                      COALESCE(SUM(result='L'),0) l FROM signals""", (start,))
    return u, s

async def all_user_ids(only_dep=False):
    q = "SELECT id FROM users" + (" WHERE deposited=1" if only_dep else "")
    return [r["id"] for r in await _all(q)]

async def meta_get(k):
    r = await _one("SELECT v FROM meta WHERE k=?", (k,)); return r["v"] if r else None
async def meta_set(k, v): await _run("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, v))


# ───────────── тарифы, кредиты, платежи ─────────────
async def get_user_by(q):
    q = str(q).strip().lstrip("@")
    if q.isdigit(): return await get_user(int(q))
    return await _one("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (q,))

async def add_credits(uid, n): await _run("UPDATE users SET credits=COALESCE(credits,0)+? WHERE id=?", (n, uid))
async def consume_credit(uid):
    return (await _run("UPDATE users SET credits=credits-1 WHERE id=? AND credits>0", (uid,)))[1] > 0
async def give_free(uid):
    return (await _run("UPDATE users SET credits=COALESCE(credits,0)+?, free_given=1 WHERE id=? AND COALESCE(free_given,0)=0",
                       (FREE_SIGNALS, uid)))[1] > 0

async def set_pro(uid, days):
    u = await get_user(uid); now = int(time.time())
    until = max(now, (u or {}).get("pro_until") or 0) + days * 86400
    await _run("UPDATE users SET pro_until=? WHERE id=?", (until, uid)); return until
async def revoke_pro(uid): await _run("UPDATE users SET pro_until=0 WHERE id=?", (uid,))
async def pros():
    return await _all("SELECT id,username,first_name,pro_until FROM users WHERE pro_until>? ORDER BY pro_until", (int(time.time()),))

async def expiring(now, soon):
    return await _all("SELECT * FROM users WHERE pro_until>? AND pro_until<=? AND COALESCE(pro_notified,0)<>pro_until", (now, soon))
async def mark_notified(uid, until): await _run("UPDATE users SET pro_notified=? WHERE id=?", (until, uid))
async def expired_unsent(now):
    return await _all("SELECT * FROM users WHERE pro_until>0 AND pro_until<=? AND COALESCE(pro_exp_sent,0)<>pro_until", (now,))
async def mark_exp_sent(uid, until): await _run("UPDATE users SET pro_exp_sent=? WHERE id=?", (until, uid))

async def add_payment(uid, kind, amount, invoice_id, status):
    return (await _run("INSERT INTO payments(user_id,kind,amount,invoice_id,status,created,paid_at) VALUES(?,?,?,?,?,?,?)",
                       (uid, kind, amount, invoice_id, status, int(time.time()), int(time.time()) if status == "paid" else None)))[0]
async def pending_crypto(since):
    return await _all("SELECT * FROM payments WHERE kind='crypto' AND status='pending' AND created>?", (since,))
async def mark_paid(invoice_id):
    return (await _run("UPDATE payments SET status='paid', paid_at=? WHERE invoice_id=? AND status='pending'", (int(time.time()), invoice_id)))[1] > 0
async def mark_expired(invoice_id): await _run("UPDATE payments SET status='expired' WHERE invoice_id=? AND status='pending'", (invoice_id,))
async def payments_last(n=10):
    return await _all("SELECT p.*, u.username FROM payments p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT ?", (n,))
async def money():
    r = await _one("""SELECT COALESCE(SUM(CASE WHEN kind='crypto' AND status='paid' THEN amount END),0) usdt,
                      COALESCE(SUM(kind='stars' AND status='paid'),0) stars_n,
                      COALESCE(SUM(kind='crypto' AND status='paid'),0) crypto_n FROM payments""")
    p = await _one("SELECT COUNT(*) n FROM users WHERE pro_until>?", (int(time.time()),))
    return dict(r, pro=p["n"])

async def profile_stats(uid):
    rows = await _all("SELECT pair,result FROM signals WHERE user_id=? AND result IN('W','L','D') ORDER BY id", (uid,))
    best = cur = 0; per = {}
    for r in rows:
        p = per.setdefault(r["pair"], [0, 0]); p[1] += 1
        if r["result"] == "W": cur += 1; best = max(best, cur); p[0] += 1
        elif r["result"] == "L": cur = 0
    bp = None
    for pair, (w, n) in per.items():
        if n >= 3:
            wr = w / n
            if bp is None or wr > bp["wr"] / 100 or (wr == bp["wr"] / 100 and n > bp["n"]): bp = dict(pair=pair, wr=round(wr * 100), n=n)
    return dict(best_streak=best, cur_streak=cur, best_pair=bp, last10=[r["result"] for r in rows[-10:]])
