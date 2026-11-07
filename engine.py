import os, time, asyncio
from datetime import datetime, timezone
from aiohttp import ClientSession, ClientTimeout

TD_KEY = os.environ["TWELVE_API_KEY"]
TTL = 20
HIGHER = {"1min": "5min", "5min": "15min", "15min": "1h", "30min": "1h", "1h": "4h"}
HNAME = {"5min": "5 мин", "15min": "15 мин", "1h": "1 час"}
CUR = {"EUR/USD": ("EUR", "USD"), "GBP/USD": ("GBP", "USD"), "USD/JPY": ("USD", "JPY"),
       "AUD/USD": ("AUD", "USD"), "BTC/USD": ("USD",), "ETH/USD": ("USD",)}

LANGS = ("ru", "uz", "en")
R = {
 "ha_bull": ("Heikin Ashi: {n} зелёных свечей подряд", "Heikin Ashi: ketma-ket {n} ta yashil sham", "Heikin Ashi: {n} green candles in a row"),
 "ha_bear": ("Heikin Ashi: {n} красных свечей подряд", "Heikin Ashi: ketma-ket {n} ta qizil sham", "Heikin Ashi: {n} red candles in a row"),
 "ha_nolow": ("Свеча Heikin Ashi без нижней тени: сильный рост", "Heikin Ashi shami pastki soyasiz: kuchli o'sish", "Heikin Ashi candle has no lower wick: strong rise"),
 "ha_noup": ("Свеча Heikin Ashi без верхней тени: сильное падение", "Heikin Ashi shami yuqori soyasiz: kuchli pasayish", "Heikin Ashi candle has no upper wick: strong fall"),
 "ema_up": ("EMA9 выше EMA21", "EMA9 EMA21 dan yuqori", "EMA9 is above EMA21"),
 "ema_dn": ("EMA9 ниже EMA21", "EMA9 EMA21 dan past", "EMA9 is below EMA21"),
 "macd_up": ("MACD выше сигнальной линии", "MACD signal chizig'idan yuqori", "MACD is above the signal line"),
 "macd_dn": ("MACD ниже сигнальной линии", "MACD signal chizig'idan past", "MACD is below the signal line"),
 "rsi_os": ("RSI {r}: перепроданность", "RSI {r}: haddan tashqari sotilgan", "RSI {r}: oversold"),
 "rsi_ob": ("RSI {r}: перекупленность", "RSI {r}: haddan tashqari sotib olingan", "RSI {r}: overbought"),
 "rsi_n": ("RSI {r}: нейтрально", "RSI {r}: neytral", "RSI {r}: neutral"),
 "st_up": ("Супертренд: вверх", "Supertrend: yuqoriga", "Supertrend: up"),
 "st_dn": ("Супертренд: вниз", "Supertrend: pastga", "Supertrend: down"),
 "st_fresh": (", свежий разворот", ", yangi burilish", ", fresh reversal"),
 "dc_hi": ("Дончиан: пробой верхней границы канала", "Donchian: kanalning yuqori chegarasi yorib o'tildi", "Donchian: upper channel breakout"),
 "dc_lo": ("Дончиан: пробой нижней границы канала", "Donchian: kanalning pastki chegarasi yorib o'tildi", "Donchian: lower channel breakout"),
 "dc_up": ("Дончиан: цена в верхней половине канала", "Donchian: narx kanalning yuqori yarmida", "Donchian: price in the upper half of the channel"),
 "dc_dn": ("Дончиан: цена в нижней половине канала", "Donchian: narx kanalning pastki yarmida", "Donchian: price in the lower half of the channel"),
 "mis": ("Супертренд и Heikin Ashi расходятся: тренд не подтверждён", "Supertrend va Heikin Ashi mos kelmayapti: trend tasdiqlanmadi", "Supertrend and Heikin Ashi disagree: trend not confirmed"),
 "flat": ("Рынок во флэте: волатильность слишком низкая для уверенного входа", "Bozor flatda: kirish uchun o'zgaruvchanlik juda past", "Market is flat: volatility is too low for a confident entry"),
 "hn_5min": ("5 мин", "5 daq", "5 min"), "hn_15min": ("15 мин", "15 daq", "15 min"), "hn_1h": ("1 час", "1 soat", "1 hour"), "hn_30min": ("30 мин", "30 daq", "30 min"), "hn_4h": ("4 часа", "4 soat", "4 hours"),
 "htf_against": ("Таймфрейм {tf} показывает {d}, это против сигнала", "{tf} taymfreymi {d} ko'rsatmoqda, bu signalga qarshi", "The {tf} timeframe shows {d}, which is against the signal"),
 "htf_ok": ("Таймфрейм {tf} подтверждает направление", "{tf} taymfreymi yo'nalishni tasdiqlaydi", "The {tf} timeframe confirms the direction"),
 "htf_neutral": ("Таймфрейм {tf} нейтрален", "{tf} taymfreymi neytral", "The {tf} timeframe is neutral"),
 "htf_na": ("Старший таймфрейм сейчас недоступен", "Yuqori taymfreym hozir mavjud emas", "Higher timeframe is unavailable right now"),
 "news": ("Важная новость: {msg}. Вход не рекомендуется", "Muhim yangilik: {msg}. Kirish tavsiya etilmaydi", "High-impact news: {msg}. Entry is not recommended"),
 "news_in": ("через {n} мин", "{n} daqiqadan keyin", "in {n} min"),
 "news_now": ("только что вышла", "hozirgina chiqdi", "just released"),
 "contra": ("Сигналы противоречат друг другу, лучше не входить", "Signallar bir-biriga zid, kirmagan ma'qul", "Signals contradict each other, better not to enter"),
}
def tr(lang, key, **kw):
    i = LANGS.index(lang) if lang in LANGS else 0
    return R[key][i].format(**kw)

BINANCE = {"BTC/USD": "BTCUSDT", "ETH/USD": "ETHUSDT"}
BIV = {"1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m", "1h": "1h", "4h": "4h"}

class DataError(Exception): pass

_cache, _locks, _sess = {}, {}, None
def session():
    global _sess
    if _sess is None or _sess.closed: _sess = ClientSession(timeout=ClientTimeout(total=12))
    return _sess

async def candles(pair, tf, fresh=False):
    key = (pair, tf); ttl = 2 if fresh else TTL
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl: return hit[1]
    async with _locks.setdefault(key, asyncio.Lock()):
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl: return hit[1]
        if pair in BINANCE:
            try:
                async with session().get("https://api.binance.com/api/v3/klines",
                                         params=dict(symbol=BINANCE[pair], interval=BIV[tf], limit=120)) as r:
                    k = await r.json()
                if isinstance(k, list) and k:
                    out = [dict(t=str(x[0]), o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4])) for x in k]
                    _cache[key] = (time.time(), out); return out
            except Exception:
                pass
        try:
            async with session().get("https://api.twelvedata.com/time_series", params=dict(
                    symbol=pair, interval=tf, outputsize=120, apikey=TD_KEY, order="ASC")) as r:
                data = await r.json()
        except Exception:
            if hit: return hit[1]
            raise DataError("Нет связи с источником котировок")
        if "values" not in data:
            if hit: return hit[1]
            raise DataError(data.get("message", "Нет данных по котировкам"))
        out = [dict(t=v["datetime"], o=float(v["open"]), h=float(v["high"]), l=float(v["low"]), c=float(v["close"]))
               for v in data["values"]]
        _cache[key] = (time.time(), out); return out

def heikin(cs):
    out = []
    for i, c in enumerate(cs):
        hc = (c["o"] + c["h"] + c["l"] + c["c"]) / 4
        ho = (c["o"] + c["c"]) / 2 if i == 0 else (out[-1]["o"] + out[-1]["c"]) / 2
        out.append(dict(o=ho, c=hc, h=max(c["h"], ho, hc), l=min(c["l"], ho, hc)))
    return out

def ema(v, n):
    k, e, out = 2 / (n + 1), v[0], []
    for x in v: e = x * k + e * (1 - k); out.append(e)
    return out

def rsi(c, n=14):
    g = l = 0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]; g += max(d, 0); l += max(-d, 0)
    g, l = g / n, l / n
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]; g = (g * (n - 1) + max(d, 0)) / n; l = (l * (n - 1) + max(-d, 0)) / n
    return 100 if l == 0 else 100 - 100 / (1 + g / l)

def atr_series(cs, n=10):
    trs = []
    for i, c in enumerate(cs):
        if i == 0: trs.append(c["h"] - c["l"]); continue
        pc = cs[i - 1]["c"]; trs.append(max(c["h"] - c["l"], abs(c["h"] - pc), abs(c["l"] - pc)))
    atr, a = [], sum(trs[:n]) / n
    for i, t in enumerate(trs):
        if i < n: atr.append(sum(trs[:i + 1]) / (i + 1))
        else: a = (a * (n - 1) + t) / n; atr.append(a)
    return atr

def supertrend(cs, n=10, m=3.0):
    atr = atr_series(cs, n); up, fu, fl, age, out = True, None, None, 0, []
    for i, c in enumerate(cs):
        hl = (c["h"] + c["l"]) / 2; bu, bl = hl + m * atr[i], hl - m * atr[i]
        if i == 0: fu, fl = bu, bl
        else:
            pc = cs[i - 1]["c"]
            fu = bu if (bu < fu or pc > fu) else fu
            fl = bl if (bl > fl or pc < fl) else fl
            if up and c["c"] < fl: up = False; age = 0
            elif (not up) and c["c"] > fu: up = True; age = 0
            else: age += 1
        out.append((fl if up else fu, up, age))
    return out

def donchian(cs, n=20):
    w = cs[-n - 1:-1]
    hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
    return hi, lo, (hi + lo) / 2

def score(ha, raw):
    cl = [x["c"] for x in ha]
    e9, e21 = ema(cl, 9), ema(cl, 21)
    macd = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]; sig = ema(macd, 9)
    r = rsi(cl); s, why = 0.0, []
    last = ha[-1]; eps = (last["h"] - last["l"]) * 0.03; bull = last["c"] > last["o"]
    n = 0
    for x in reversed(ha):
        if (x["c"] > x["o"]) == bull: n += 1
        else: break
    s += 1 if bull else -1
    why.append(("ha_bull" if bull else "ha_bear", dict(n=n)))
    if bull and last["o"] - last["l"] <= eps: s += 1; why.append(("ha_nolow", {}))
    if not bull and last["h"] - last["o"] <= eps: s -= 1; why.append(("ha_noup", {}))
    if n >= 3: s += 0.5 if bull else -0.5
    if e9[-1] > e21[-1]: s += 1; why.append(("ema_up", {}))
    else: s -= 1; why.append(("ema_dn", {}))
    if macd[-1] > sig[-1]: s += 1; why.append(("macd_up", {}))
    else: s -= 1; why.append(("macd_dn", {}))
    if r < 32: s += 1.5; why.append(("rsi_os", dict(r=f"{r:.0f}")))
    elif r > 68: s -= 1.5; why.append(("rsi_ob", dict(r=f"{r:.0f}")))
    else: why.append(("rsi_n", dict(r=f"{r:.0f}")))
    v, stup, age = supertrend(ha)[-1]
    s += 1.5 if stup else -1.5
    why.append(("st_up" if stup else "st_dn", dict(fresh=age <= 2)))
    if age <= 2: s += 0.5 if stup else -0.5
    dh, dl, dm = donchian(raw); px = raw[-1]["c"]
    if px > dh: s += 1; why.append(("dc_hi", {}))
    elif px < dl: s -= 1; why.append(("dc_lo", {}))
    elif px > dm: s += 0.5; why.append(("dc_up", {}))
    else: s -= 0.5; why.append(("dc_dn", {}))
    atr = atr_series(raw, 14); flat = atr[-1] < 0.6 * (sum(atr[-50:]) / len(atr[-50:]))
    return dict(score=s, why=why, rsi=round(r, 1), aligned=(bull == stup), flat=flat)

def direction(s): return "WAIT" if abs(s) < 2.5 else ("CALL" if s > 0 else "PUT")

_news = (0, [])
async def news_block(pair, lang="ru"):
    global _news
    if time.time() - _news[0] > 1800:
        try:
            async with session().get("https://nfs.faireconomy.media/ff_calendar_thisweek.json") as r:
                _news = (time.time(), await r.json(content_type=None))
        except Exception:
            _news = (time.time() - 1500, _news[1])
    cur = CUR.get(pair, ("USD",)); now = datetime.now(timezone.utc)
    for e in _news[1]:
        try:
            if e.get("impact") != "High" or e.get("country") not in cur: continue
            d = (datetime.fromisoformat(e["date"]).astimezone(timezone.utc) - now).total_seconds() / 60
        except Exception: continue
        if -10 <= d <= 20:
            when = tr(lang, "news_in", n=round(d)) if d > 0 else tr(lang, "news_now")
            return f"{e['country']} {e['title']} ({when})"
    return None

async def analyze(pair, tf, lang="ru"):
    cs = await candles(pair, tf)
    if len(cs) < 40: raise DataError("Мало данных для анализа")
    m = score(heikin(cs), cs); d = direction(m["score"]); why = list(m["why"]); strength = min(abs(m["score"]) / 6.5, 1)
    if d != "WAIT" and not m["aligned"]:
        d = "WAIT"; why.append(("mis", {}))
    if d != "WAIT" and m["flat"]:
        d = "WAIT"; why.append(("flat", {}))
    hi = HIGHER[tf]; hn = tr(lang, "hn_" + hi)
    try:
        hc = await candles(pair, hi); hs = score(heikin(hc), hc); hd = direction(hs["score"])
        if d != "WAIT" and hd != "WAIT" and hd != d:
            why.append(("htf_against", dict(tf=hn, d=hd))); d = "WAIT"
        elif d != "WAIT" and hd == d:
            why.append(("htf_ok", dict(tf=hn))); strength = min(strength * 1.15, 1)
        elif d != "WAIT":
            why.append(("htf_neutral", dict(tf=hn))); strength *= 0.85
    except DataError:
        why.append(("htf_na", {}))
    nb = await news_block(pair, lang)
    if nb and d != "WAIT":
        d = "WAIT"; why.insert(0, ("news", dict(msg=nb)))
    if d == "WAIT" and not nb and abs(m["score"]) < 2.5:
        why.append(("contra", {}))
    reasons = []
    for k, kw in why:
        kw = dict(kw); fresh = kw.pop("fresh", False)
        txt = tr(lang, k, **kw)
        if fresh: txt += tr(lang, "st_fresh")
        reasons.append(txt)
    return dict(direction=d, strength=round(strength * 100), rsi=m["rsi"], reasons=reasons, entry=cs[-1]["c"])
