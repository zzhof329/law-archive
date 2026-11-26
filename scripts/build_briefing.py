"""
나스닥·코스피 데일리 브리핑 생성 스크립트

1) yfinance로 지수·종목·섹터·매크로 시세 수집
2) Google News RSS로 시장 뉴스 수집
3) (선택) 한국은행 ECOS API로 국고채 3년 금리 수집
4) Claude API로 헤드라인·시장 코멘트·뉴스 한줄평 작성
5) docs/data/latest.json + archive/ 에 저장 → GitHub Pages가 그대로 서비스

환경변수
  ANTHROPIC_API_KEY  (없으면 규칙 기반 요약으로 대체)
  BRIEF_MODEL        매일 브리핑 모델 (기본값: claude-haiku-5-5)
  CLAUDE_MODEL       심층 분석·달력 모델 (기본값: claude-sonnet-5-5)
  ECOS_API_KEY       (선택)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import time
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
import requests
import yfinance as yf

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
KST = ZoneInfo("Asia/Seoul")

# 매일 브리핑은 가벼운 Haiku, 웹 검색이 필요한 심층 분석·달력은 Sonnet
BRIEF_MODEL = os.getenv("BRIEF_MODEL") or "claude-haiku-5-5"
DEEP_MODEL = os.getenv("CLAUDE_MODEL") or "claude-sonnet-5-5"

# ── 수집 대상 (원하는 대로 수정하세요) ─────────────────────────────
INDICES = [
    ("^IXIC", "나스닥 종합"),
    ("^NDX", "나스닥 100"),
    ("^GSPC", "S&P 500"),
    ("^DJI", "다우존스"),
    ("^SOX", "필라델피아 반도체"),
    ("^VIX", "VIX 변동성"),
    ("^KS11", "코스피"),
    ("^KQ11", "코스닥"),
]

# 시가총액 상위 10개를 매번 자동으로 고르기 위한 후보군 (순위가 바뀌어도 따라감)
# 한국은 우선주(삼성전자우 등)를 빼고 보통주 기준
TOP_N = 10
US_POOL = [
    ("NVDA", "엔비디아"), ("MSFT", "마이크로소프트"), ("AAPL", "애플"), ("GOOGL", "알파벳"),
    ("AMZN", "아마존"), ("META", "메타"), ("AVGO", "브로드컴"), ("TSLA", "테슬라"),
    ("BRK-B", "버크셔 해서웨이"), ("LLY", "일라이 릴리"), ("JPM", "JP모건"), ("WMT", "월마트"),
    ("ORCL", "오라클"), ("V", "비자"), ("MA", "마스터카드"), ("NFLX", "넷플릭스"),
    ("XOM", "엑슨모빌"), ("COST", "코스트코"), ("PLTR", "팔란티어"), ("AMD", "AMD"),
    ("UNH", "유나이티드헬스"), ("JNJ", "존슨앤드존슨"),
]
KR_POOL = [
    ("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("373220.KS", "LG에너지솔루션"),
    ("207940.KS", "삼성바이오로직스"), ("005380.KS", "현대차"), ("012450.KS", "한화에어로스페이스"),
    ("105560.KS", "KB금융"), ("000270.KS", "기아"), ("068270.KS", "셀트리온"),
    ("035420.KS", "NAVER"), ("329180.KS", "HD현대중공업"), ("055550.KS", "신한지주"),
    ("034020.KS", "두산에너빌리티"), ("012330.KS", "현대모비스"), ("028260.KS", "삼성물산"),
    ("042660.KS", "한화오션"), ("009540.KS", "HD한국조선해양"), ("005490.KS", "POSCO홀딩스"),
    ("006400.KS", "삼성SDI"), ("032830.KS", "삼성생명"), ("402340.KS", "SK스퀘어"),
    ("086790.KS", "하나금융지주"), ("035720.KS", "카카오"), ("010130.KS", "고려아연"),
]


KOSDAQ_POOL = [
    ("247540.KQ", "에코프로비엠"), ("086520.KQ", "에코프로"), ("196170.KQ", "알테오젠"), ("028300.KQ", "HLB"),
    ("277810.KQ", "레인보우로보틱스"), ("141080.KQ", "리가켐바이오"), ("298380.KQ", "에이비엘바이오"),
    ("087010.KQ", "펩트론"), ("000250.KQ", "삼천당제약"), ("214450.KQ", "파마리서치"), ("145020.KQ", "휴젤"),
    ("214150.KQ", "클래시스"), ("058470.KQ", "리노공업"), ("039030.KQ", "이오테크닉스"), ("263750.KQ", "펄어비스"),
    ("357780.KQ", "솔브레인"), ("403870.KQ", "HPSP"), ("095340.KQ", "ISC"), ("240810.KQ", "원익IPS"),
    ("293490.KQ", "카카오게임즈"), ("035900.KQ", "JYP Ent."), ("041510.KQ", "에스엠"), ("066970.KQ", "엘앤에프"),
    ("237690.KQ", "에스티팜"), ("950160.KQ", "코오롱티슈진"), ("310210.KQ", "보로노이"), ("108490.KQ", "로보티즈"),
    ("064760.KQ", "티씨케이"), ("189300.KQ", "인텔리안테크"), ("214370.KQ", "케어젠"),
]

# 주요 ETF: (티커, 이름, 무엇을 따라가는지)
# 같은 지수를 따라가는 상품은 하나만, 레버리지·인버스는 제외, 서로 다른 자산·테마로 10개씩
US_ETFS = [
    ("VOO", "뱅가드 S&P 500", "S&P 500 (대형주)"), ("QQQ", "인베스코 QQQ", "나스닥 100 (기술주)"),
    ("DIA", "SPDR 다우존스", "다우존스 30 (우량주)"), ("IWM", "아이셰어즈 러셀 2000", "러셀 2000 (소형주)"),
    ("SCHD", "슈왑 미국 배당", "배당 성장주"), ("SOXX", "아이셰어즈 반도체", "반도체"),
    ("JEPI", "JP모건 프리미엄 인컴", "커버드콜 (월배당)"), ("TLT", "아이셰어즈 미국 장기채", "미국 20년+ 국채"),
    ("GLD", "SPDR 금", "금"), ("IBIT", "아이셰어즈 비트코인", "비트코인 현물"),
]
KR_ETFS = [
    ("069500.KS", "KODEX 200", "코스피 200"), ("229200.KS", "KODEX 코스닥150", "코스닥 150"),
    ("360750.KS", "TIGER 미국S&P500", "S&P 500"), ("133690.KS", "TIGER 미국나스닥100", "나스닥 100"),
    ("458730.KS", "TIGER 미국배당다우존스", "미국 배당 성장주"),
    ("381180.KS", "TIGER 미국필라델피아반도체나스닥", "미국 반도체"),
    ("453850.KS", "ACE 미국30년국채액티브(H)", "미국 장기 국채 (환헤지)"), ("411060.KS", "ACE KRX금현물", "금 현물"),
    ("459580.KS", "KODEX CD금리액티브(합성)", "CD 금리 (파킹용)"), ("371460.KS", "TIGER 차이나전기차SOLACTIVE", "중국 전기차"),
]


def fetch_etfs() -> dict:
    out = {}
    for mk, table in (("us", US_ETFS), ("kr", KR_ETFS)):
        rows = fetch_quotes([(t, n) for t, n, _ in table])
        desc = {t: d for t, _, d in table}
        for r in rows:
            r["desc"] = desc.get(r["symbol"], "")
        out[mk] = rows
        print(f"[etf] {mk}: {len(rows)}/{len(table)}개")
    return out


def top_by_market_cap(pool: list[tuple], n: int = TOP_N) -> tuple[list[tuple], dict]:
    """후보군의 시가총액을 조회해 상위 n개를 고른다. 조회가 안 되면 후보군 순서대로."""
    caps = {}
    for symbol, _ in pool:
        for attempt in range(2):
            try:
                cap = yf.Ticker(symbol).fast_info["market_cap"]
                if cap and cap > 0:
                    caps[symbol] = float(cap)
                break
            except Exception as e:  # noqa: BLE001
                if attempt:
                    print(f"[cap] {symbol}: {e}")
                time.sleep(1)
    if len(caps) < n:
        print(f"[cap] 시가총액을 {len(caps)}개만 받아 일부는 후보군 순서로 채웁니다")
    ranked = sorted(pool, key=lambda r: -caps.get(r[0], -pool.index(r)))
    return ranked[:n], caps


# 미국: SPDR 섹터 ETF / 한국: KODEX 섹터 ETF (섹터 흐름의 대용치)
US_SECTORS = [
    ("XLK", "기술"), ("XLC", "커뮤니케이션"), ("XLY", "임의소비재"),
    ("XLF", "금융"), ("XLV", "헬스케어"), ("XLI", "산업재"),
    ("XLE", "에너지"), ("XLP", "필수소비재"), ("XLU", "유틸리티"),
]
KR_SECTORS = [
    ("091160.KS", "반도체"), ("305720.KS", "2차전지"), ("091180.KS", "자동차"),
    ("091170.KS", "은행"), ("266420.KS", "헬스케어"), ("117700.KS", "건설"),
    ("117460.KS", "에너지화학"),
]

# unit: 화면 표시 방식 (krw, pct=금리, usd, idx)
MACRO = [
    ("KRW=X", "원/달러 환율", "krw"),
    ("JPYKRW=X", "원/엔 (100엔)", "krw100"),
    ("EURKRW=X", "원/유로", "krw"),
    ("CNYKRW=X", "원/위안", "krw"),
    ("JPY=X", "엔/달러", "jpy"),
    ("DX-Y.NYB", "달러 인덱스", "idx"),
    ("^TNX", "미국채 10년", "pct"),
    ("^IRX", "미국채 3개월", "pct"),
    ("CL=F", "WTI 유가", "usd"),
    ("GC=F", "금", "usd"),
]

NEWS_QUERIES = {
    "us": "나스닥 OR 뉴욕증시 when:1d",
    "kr": "코스피 OR 코스닥 when:1d",
}


# ── 코인 ─────────────────────────────────────────────────────────
# 스테이블코인(USDT·USDC 등)은 가격이 1달러에 고정돼 있어 제외
COINS = [("BTC", "비트코인"), ("ETH", "이더리움"), ("XRP", "엑스알피(리플)"), ("BNB", "바이낸스코인"),
         ("SOL", "솔라나"), ("DOGE", "도지코인"), ("TRX", "트론"), ("ADA", "에이다"),
         ("LINK", "체인링크"), ("AVAX", "아발란체")]
UPBIT_MISSING = {"BNB"}  # 업비트 원화 시장에 없는 코인


def fetch_crypto(usdkrw: float | None) -> dict:
    """달러 시세(yfinance) + 원화 시세(업비트) + 김치 프리미엄 + 공포·탐욕 지수"""
    rows = fetch_quotes([(f"{c}-USD", name) for c, name in COINS])
    krw = {}
    try:
        markets = ",".join(f"KRW-{c}" for c, _ in COINS if c not in UPBIT_MISSING)
        r = requests.get(f"https://api.upbit.com/v1/ticker?markets={markets}", timeout=15)
        for t in r.json():
            krw[t["market"].split("-")[1]] = {"price": t["trade_price"], "pct": round(t["signed_change_rate"] * 100, 2)}
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] 업비트 실패: {e}")
    coins = []
    for r in rows:
        c = r["symbol"].split("-")[0]
        item = {**r, "symbol": c}
        if c in krw:
            item["krw"] = krw[c]["price"]
            item["krw_pct"] = krw[c]["pct"]
            if usdkrw:
                item["premium"] = round((krw[c]["price"] / (r["price"] * usdkrw) - 1) * 100, 2)
        elif usdkrw:
            item["krw_est"] = round(r["price"] * usdkrw)  # 업비트에 없으면 환율로 환산
        coins.append(item)
    fng = None
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=2", timeout=15).json()["data"]
        label = {"Extreme Fear": "극단적 공포", "Fear": "공포", "Neutral": "중립", "Greed": "탐욕",
                 "Extreme Greed": "극단적 탐욕"}
        fng = {"value": int(d[0]["value"]), "label": label.get(d[0]["value_classification"], d[0]["value_classification"]),
               "prev": int(d[1]["value"]) if len(d) > 1 else None}
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] 공포·탐욕 지수 실패: {e}")
    print(f"[crypto] 코인 {len(coins)}개, 업비트 {len(krw)}개, 공포·탐욕 {fng and fng['value']}")
    return {"coins": coins, "fng": fng, "usdkrw": usdkrw}


# ── 시세 ─────────────────────────────────────────────────────────
def _closes_one(symbol: str):
    """한 종목만 따로 받아오기 (일괄 다운로드에서 빠졌을 때 재시도용)"""
    for attempt in range(3):
        try:
            h = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False)
            closes = h["Close"].dropna()
            if len(closes) >= 2:
                return closes
        except Exception as e:  # noqa: BLE001
            print(f"[retry {attempt + 1}] {symbol}: {e}")
        time.sleep(2 + attempt * 3)
    return None


def fetch_quotes(table: list[tuple]) -> list[dict]:
    tickers = [row[0] for row in table]
    try:
        df = yf.download(
            tickers, period="1mo", interval="1d", group_by="ticker",
            auto_adjust=False, progress=False, threads=False,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[download] 일괄 다운로드 실패: {e}")
        df = None
    out = []
    for row in table:
        symbol, name = row[0], row[1]
        closes = None
        try:
            closes = df[symbol]["Close"].dropna()
        except Exception:  # noqa: BLE001
            pass
        if closes is None or len(closes) < 2:
            print(f"[retry] {symbol}: 일괄 다운로드에서 빠져 따로 받아옵니다")
            closes = _closes_one(symbol)
        if closes is None:
            print(f"[skip] {symbol}: 데이터 없음")
            continue
        last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        item = {
            "symbol": symbol,
            "name": name,
            "price": round(last, 4),
            "change": round(last - prev, 4),
            "pct": round((last / prev - 1) * 100, 2),
            "date": closes.index[-1].strftime("%Y-%m-%d"),
            "spark": [round(float(v), 4) for v in closes.tail(20)],
        }
        if len(row) > 2:
            item["unit"] = row[2]
        out.append(item)
    return out


def fetch_ecos_kr3y() -> dict | None:
    """한국은행 ECOS: 국고채 3년 (통계표 817Y002 / 항목 010200000)"""
    key = os.getenv("ECOS_API_KEY")
    if not key:
        return None
    end = dt.datetime.now(KST).strftime("%Y%m%d")
    start = (dt.datetime.now(KST) - dt.timedelta(days=20)).strftime("%Y%m%d")
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/30/"
           f"817Y002/D/{start}/{end}/010200000")
    try:
        rows = requests.get(url, timeout=15).json()["StatisticSearch"]["row"]
        vals = [float(r["DATA_VALUE"]) for r in rows]
        if len(vals) < 2:
            return None
        return {
            "symbol": "KR3Y", "name": "국고채 3년", "unit": "pct",
            "price": vals[-1], "change": round(vals[-1] - vals[-2], 3),
            "pct": round((vals[-1] / vals[-2] - 1) * 100, 2),
            "date": dt.datetime.strptime(rows[-1]["TIME"], "%Y%m%d").strftime("%Y-%m-%d"),
            "spark": vals[-20:],
        }
    except Exception as e:  # noqa: BLE001
        print(f"[ecos] 실패: {e}")
        return None


# ── 뉴스 ─────────────────────────────────────────────────────────
# ── 데이터 신선도 점검 ──────────────────────────────────────────
def load_previous() -> dict:
    try:
        return json.loads((DATA_DIR / "latest.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def no_regress(rows: list[dict], prev_rows: list[dict] | None, label: str) -> list[dict]:
    """새로 받은 숫자가 이전 브리핑보다 오래된 날짜면, 이전의 더 최신 숫자를 그대로 쓴다"""
    prev = {r["symbol"]: r for r in (prev_rows or []) if isinstance(r, dict) and r.get("symbol")}
    out, seen = [], set()
    for r in rows:
        p = prev.get(r["symbol"])
        if p and p.get("date", "") > r.get("date", ""):
            print(f"[fresh] {label} {r['symbol']}: 받은 데이터({r.get('date')})가 이전({p.get('date')})보다 오래돼 이전 값 유지")
            r = {**p, **{k: v for k, v in r.items() if k in ("name", "desc", "unit")}}
        out.append(r)
        seen.add(r["symbol"])
    return out


def naver_index(code: str) -> dict | None:
    """네이버 증권 지수 일별 시세 (code: KOSPI / KOSDAQ) → 최근 마감 1건"""
    try:
        r = requests.get(f"https://m.stock.naver.com/api/index/{code}/price?pageSize=25&page=1", timeout=15,
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get("result") or rows.get("items") or []
        parsed = []
        for it in rows:
            d = str(it.get("localTradedAt") or it.get("tradeDate") or it.get("date") or "")[:10].replace(".", "-")
            c = _num(it.get("closePrice") or it.get("closeIndex"))
            if len(d) == 8 and d.isdigit():
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            if d and c:
                parsed.append((d, c))
        parsed.sort()
        if len(parsed) < 2:
            return None
        (d0, c0), (d1, c1) = parsed[-2], parsed[-1]
        return {"date": d1, "price": c1, "change": round(c1 - c0, 2), "pct": round((c1 / c0 - 1) * 100, 2),
                "spark": [c for _, c in parsed[-20:]]}
    except Exception as e:  # noqa: BLE001
        print(f"[fresh] 네이버 지수 {code} 실패: {e}")
        return None


def fix_kr_indices(indices: list[dict], kr_dates: list[str]) -> None:
    """코스피·코스닥 지수 날짜가 한국 종목 날짜보다 늦으면 네이버에서 마감가를 다시 받는다"""
    latest_kr = max(kr_dates) if kr_dates else ""
    for i in indices:
        code = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}.get(i["symbol"])
        if not code or not latest_kr or i.get("date", "") >= latest_kr:
            continue
        n = naver_index(code)
        if n and n["date"] > i.get("date", ""):
            print(f"[fresh] {i['name']}: Yahoo {i.get('date')} → 네이버 {n['date']} 마감가로 교체")
            i.update(n)
        else:
            print(f"[fresh] {i['name']}: 지수({i.get('date')})가 종목({latest_kr})보다 늦지만 대체 데이터를 받지 못했습니다")


# ── 오늘의 상승·하락 상위 ────────────────────────────────────────
def us_movers(kind: str, n: int = 10) -> list[dict]:
    """Yahoo Finance 기본 스크리너(day_gainers / day_losers): 시총 20억 달러 이상 미국 종목"""
    quotes = []
    try:
        if hasattr(yf, "screen"):
            res = yf.screen(kind, count=25)
        else:  # 예전 yfinance
            sc = yf.Screener()
            sc.set_predefined_body(kind)
            res = sc.response
        quotes = (res or {}).get("quotes", [])
    except Exception as e:  # noqa: BLE001
        print(f"[movers] 미국 {kind} 실패: {e}")
    out = []
    for q in quotes:
        pct = q.get("regularMarketChangePercent")
        if pct is None or not q.get("symbol"):
            continue
        out.append({"symbol": q["symbol"], "name": q.get("shortName") or q.get("longName") or q["symbol"],
                    "price": q.get("regularMarketPrice"), "pct": round(float(pct), 2), "cap": q.get("marketCap")})
    out.sort(key=lambda r: -r["pct"] if kind == "day_gainers" else r["pct"])
    return out[:n]


KR_SKIP = re.compile(r"스팩|ETN|레버리지|인버스|(우|우B|우C|\d우B?)$")


def kr_movers(kind: str, sosok: int, n: int = 10) -> list[dict]:
    """네이버 증권 상승/하락 순위 (sosok 0=코스피, 1=코스닥). 우선주·스팩·ETN 제외"""
    url = f"https://finance.naver.com/sise/sise_{kind}.naver?sosok={sosok}"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = "euc-kr"
        html = r.text
    except Exception as e:  # noqa: BLE001
        print(f"[movers] 네이버 {kind}/{sosok} 실패: {e}")
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        m_name = re.search(r'class="tltle"[^>]*>(.*?)</a>', tr)
        m_code = re.search(r"code=(\d{6})", tr)
        if not (m_name and m_code):
            continue
        name = re.sub(r"<[^>]+>", "", m_name.group(1)).strip()
        if KR_SKIP.search(name):
            continue
        cells = [re.sub(r"<[^>]+>|\s", "", c) for c in re.findall(r'<td class="number"[^>]*>(.*?)</td>', tr, re.S)]
        pct_cell = next((c for c in cells if c.endswith("%")), None)
        try:
            price = float(cells[0].replace(",", ""))
            pct = float(pct_cell.replace("%", "").replace("+", ""))
        except Exception:  # noqa: BLE001
            continue
        out.append({"symbol": m_code.group(1), "name": name, "price": price, "pct": pct})
        if len(out) >= n:
            break
    if not out:
        print(f"[movers] 네이버 {kind}/{sosok}: 표를 읽지 못했습니다 (페이지 구조 변경 가능)")
    return out




def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("+", ""))
    except Exception:  # noqa: BLE001
        return None


def kr_movers_api(kind: str, market: str, n: int = 10) -> list[dict]:
    """네이버 증권 모바일 데이터 (kind: up/down, market: KOSPI/KOSDAQ)"""
    url = f"https://m.stock.naver.com/api/stocks/{kind}/{market}?page=1&pageSize=40"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[movers] 네이버 API {kind}/{market} 실패: {e}")
        return []
    rows = data.get("stocks") if isinstance(data, dict) else data
    out = []
    for it in rows or []:
        name = it.get("stockName") or it.get("itemName") or ""
        code = it.get("itemCode") or it.get("reutersCode") or ""
        pct, price = _num(it.get("fluctuationsRatio")), _num(it.get("closePrice"))
        if not name or pct is None or KR_SKIP.search(name) or str(it.get("stockEndType", "stock")) not in ("stock", ""):
            continue
        out.append({"symbol": str(code)[:6], "name": name, "price": price, "pct": pct})
        if len(out) >= n:
            break
    if not out:
        print(f"[movers] 네이버 API {kind}/{market}: 받은 종목이 없습니다")
    return out


def pool_movers(pool: list[tuple], n: int = 10) -> dict:
    """대체 수단: 대형주 후보군 안에서 등락률 순으로 정렬"""
    rows = fetch_quotes(pool)
    rows = [{"symbol": r["symbol"][:6], "name": r["name"], "price": r["price"], "pct": r["pct"]} for r in rows]
    up = sorted([r for r in rows if r["pct"] > 0], key=lambda r: -r["pct"])[:n]
    down = sorted([r for r in rows if r["pct"] < 0], key=lambda r: r["pct"])[:n]
    return {"up": up, "down": down, "src": "pool"}


def fetch_movers() -> dict:
    result = {"us": {"up": us_movers("day_gainers"), "down": us_movers("day_losers"), "src": "yahoo"}}
    for key, market, sosok, pool in (("kospi", "KOSPI", 0, KR_POOL), ("kosdaq", "KOSDAQ", 1, KOSDAQ_POOL)):
        board, srcs, pool_rows = {}, {}, None
        # 상승·하락을 따로 시도: 네이버 앱 데이터 → 네이버 웹페이지 → 대형주 기준
        for side, api_kind, web_kind in (("up", "up", "rise"), ("down", "down", "fall")):
            rows, src = kr_movers_api(api_kind, market), "naver"
            if not rows:
                rows = kr_movers(web_kind, sosok)
            if not rows:
                if pool_rows is None:
                    print(f"[movers] {market} {side}: 네이버에서 받지 못해 대형주 기준으로 대체합니다")
                    pool_rows = pool_movers(pool)
                rows, src = pool_rows[side], "pool"
            board[side], srcs[side] = rows, src
        board["src"] = "pool" if "pool" in srcs.values() else "naver"
        board["src_detail"] = srcs
        result[key] = board
    for k, v in result.items():
        print(f"[movers] {k}: 상승 {len(v['up'])}개, 하락 {len(v['down'])}개 ({v.get('src_detail', v.get('src'))})")
    return result


def fetch_news(limit: int = 7) -> list[dict]:
    items, seen = [], set()
    for market, q in NEWS_QUERIES.items():
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for e in feed.entries[:limit]:
            title = re.sub(r"\s+-\s+[^-]+$", "", e.title).strip()  # 끝의 " - 언론사" 제거
            if title in seen:
                continue
            seen.add(title)
            source = getattr(getattr(e, "source", None), "title", "") or ""
            items.append({"market": market, "title": title, "link": e.link,
                          "source": source, "published": e.get("published", "")})
    return items


# ── Claude 브리핑 ────────────────────────────────────────────────
SYSTEM = """당신은 한국 개인투자자를 위한 증권사 리서치센터의 데일리 마켓 브리핑 작성자입니다.
주어진 시세·뉴스 데이터만 근거로 쓰고, 데이터에 없는 수치나 사실은 만들지 마세요.
매수·매도 권유는 하지 않습니다. 문체는 간결한 '~했다/~이다' 체.
session이 '장중'이면 열려 있는 시장은 아직 마감 전입니다. '마감했다' 대신 '○시 현재 ~% 하락 중'처럼 쓰고, 마감 결과처럼 쓰지 마세요.
전망(outlook)은 확정적 예측이 아니라 조건부 시나리오로 쓰고, 근거가 약하면 '중립'으로 두세요.
시장 이름은 정확하게 쓰세요. '뉴욕 증시', '뉴욕장', '월가', '서울 증시', '서울장', '여의도' 같은 표현 대신
'미국 증시'·'나스닥'·'S&P 500'·'다우', '한국 증시'·'코스피'·'코스닥'처럼 시장·지수 이름을 쓰세요.
반드시 아래 형식의 JSON 객체 하나만 출력하세요. 설명 문장, 마크다운 코드블록, 주석(//)은 넣지 마세요.
{
  "headline": "오늘 시장을 한 문장으로 (40자 내외)",
  "us": "미국 시장 코멘트 3~4문장 (300자 이내)",
  "kr": "한국 시장 코멘트 3~4문장 (300자 이내)",
  "macro": "환율·금리·원자재 코멘트 2~3문장 (200자 이내)",
  "crypto": "비트코인·주요 코인 흐름 2~3문장 (200자 이내). 김치 프리미엄·공포탐욕지수가 있으면 반영, 주식시장과의 연관성도 짧게",
  "watch": ["오늘/다음 거래일 체크포인트 3개. upcoming_events가 있으면 날짜와 함께 반영"],
  "drivers": ["오늘 시장이 움직인 이유 2~3개. 각 1문장, 근거(지표·뉴스·수급) 포함"],
  "outlook": {"stance": "상승 우위 또는 중립 또는 하락 우위", "horizon": "다음 거래일~1주",
              "reason": "그렇게 판단한 근거 2~3문장 (technicals·일정·뉴스 근거)",
              "scenarios": [{"name": "기본", "likelihood": "높음 또는 중간 또는 낮음", "direction": "up 또는 flat 또는 down (이 시나리오에서 지수가 가는 방향)", "desc": "어떤 조건에서 어떤 흐름인지 1~2문장"},
                            {"name": "상방", "likelihood": "...", "desc": "..."}, {"name": "하방", "likelihood": "...", "desc": "..."}],
              "levels": ["볼 만한 지수 수준 1~3개. technicals의 20일 고점·저점·이동평균 근거, 예: 코스피 20일 이동평균 5,050선"]},
  "tags": ["아카이브 분류용 주제 태그 3~5개. 짧은 명사, 예: 반도체, 환율, 금리, 실적, 2차전지, 유가"],
  "news_notes": [{"i": 0, "note": "중요한 뉴스 최대 6개에 대한 시장 관점 한줄평. i는 뉴스 번호(숫자)"}]
}"""


def write_with_claude(payload: dict) -> dict | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    from anthropic import Anthropic

    client = Anthropic()
    msg = client.messages.create(
        model=BRIEF_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    if msg.stop_reason == "max_tokens":
        print("[claude] 답이 길어서 중간에 잘렸습니다. max_tokens를 늘리거나 분량을 줄이세요.")
    return parse_json_loose(text)


CITE_RE = re.compile(r"</?cite[^>]*>")


def parse_json_loose(text: str) -> dict | None:
    cleaned = CITE_RE.sub("", re.sub(r"```(?:json)?", "", text))
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        print(f"[claude] JSON을 찾지 못함. 응답 앞부분: {text[:300]!r}")
        return None
    body = cleaned[start:end + 1]
    for candidate in (body, re.sub(r"//[^\n\"]*$", "", body, flags=re.M), re.sub(r",\s*([}\]])", r"\1", body)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    print(f"[claude] JSON 파싱 실패, 기본 요약 사용. 응답 앞부분: {text[:300]!r}")
    return None


def fallback_briefing(indices: list[dict]) -> dict:
    by = {i["symbol"]: i for i in indices}

    def join(*syms):
        return ", ".join(f"{by[s]['name']} {by[s]['pct']:+.2f}%" for s in syms if s in by)

    us, kr = join("^IXIC", "^GSPC", "^SOX"), join("^KS11", "^KQ11")
    return {
        "headline": join("^IXIC", "^KS11") or join("^GSPC", "^KS11") or "오늘의 시장 브리핑",
        "us": f"{us}로 마감했다." if us else "",
        "kr": f"{kr}로 마감했다." if kr else "",
        "macro": "",
        "watch": [],
        "tags": [],
        "news_notes": [],
    }



# ── 역대 월별 등락 (시즌성) ──────────────────────────────────────
SEASON_INDICES = [("^IXIC", "나스닥 종합"), ("^NDX", "나스닥 100"), ("^KS11", "코스피"), ("^KQ11", "코스닥")]


def build_seasonality() -> None:
    """지수별 월간 수익률을 연도×월 표로 저장 → docs/data/seasonality.json"""
    out = []
    now = dt.datetime.now(KST)
    for symbol, name in SEASON_INDICES:
        try:
            h = yf.Ticker(symbol).history(period="max", interval="1mo", auto_adjust=False)
            closes = h["Close"].dropna()
            closes = closes[~closes.index.duplicated(keep="last")]
            rets = closes.pct_change().dropna() * 100
        except Exception as e:  # noqa: BLE001
            print(f"[season] {symbol} 실패: {e}")
            continue
        years: dict[str, list] = {}
        for ts, r in rets.items():
            y, m = str(ts.year), ts.month
            years.setdefault(y, [None] * 12)[m - 1] = round(float(r), 2)
        # 진행 중인 이번 달은 통계에서 제외
        cur_y, cur_m = str(now.year), now.month
        stats = []
        for m in range(12):
            vals = [row[m] for y, row in years.items() if row[m] is not None and not (y == cur_y and m + 1 == cur_m)]
            if not vals:
                stats.append(None)
                continue
            vals_sorted = sorted(vals)
            mid = len(vals_sorted) // 2
            median = vals_sorted[mid] if len(vals_sorted) % 2 else (vals_sorted[mid - 1] + vals_sorted[mid]) / 2
            stats.append({
                "avg": round(sum(vals) / len(vals), 2),
                "median": round(median, 2),
                "up": round(sum(v > 0 for v in vals) / len(vals) * 100),
                "n": len(vals),
                "best": round(max(vals), 2),
                "worst": round(min(vals), 2),
            })
        out.append({"symbol": symbol, "name": name, "current": f"{cur_y}-{cur_m:02d}",
                    "years": dict(sorted(years.items())), "stats": stats})
        print(f"[season] {name}: {min(years)}~{max(years)}년")
    if out:
        doc = {"updated": now.isoformat(timespec="minutes"), "indices": out}
        (DATA_DIR / "seasonality.json").write_text(json.dumps(doc, ensure_ascii=False), "utf-8")


# ── 경제 일정 달력 ──────────────────────────────────────────────
# ── 지수 위치(20일 기준) ──
def technicals(indices: list[dict]) -> list[dict]:
    out = []
    for i in indices:
        if i["symbol"] not in ("^IXIC", "^NDX", "^SOX", "^KS11", "^KQ11"):
            continue
        sp = i.get("spark") or []
        if len(sp) < 10:
            continue
        last, hi, lo = sp[-1], max(sp), min(sp)
        ma20, ma5 = sum(sp) / len(sp), sum(sp[-5:]) / 5
        out.append({"name": i["name"], "close": round(last, 2), "high20": round(hi, 2), "low20": round(lo, 2),
                    "ma20": round(ma20, 2), "ma5": round(ma5, 2),
                    "from_high20_pct": round((last / hi - 1) * 100, 2), "vs_ma20_pct": round((last / ma20 - 1) * 100, 2),
                    "ret5_pct": round((last / sp[-6] - 1) * 100, 2) if len(sp) >= 6 else None})
    return out


# ── 큰 변동일 심층 분석 ──────────────────────────────────────────
ANALYSIS_INDEX_MOVE = 2.0   # 지수 ±2% 이상
ANALYSIS_VIX_JUMP = 15.0    # VIX +15% 이상
ANALYSIS_SYSTEM = """당신은 한국 개인투자자를 위한 증권사 시황 애널리스트입니다.
시장이 크게 움직인 이유를 웹 검색으로 실제 보도를 확인해 분석합니다.
- triggers에 있는 시장(us=미국 증시, kr=한국 증시)마다 parts를 하나씩 쓰세요. 미국은 가장 최근(전날 밤) 거래일, 한국은 가장 최근 거래일 기준입니다.
- 코인(market "crypto") 파트는 항상 하나 쓰세요. 비트코인 중심으로, 주식시장 급변과의 연관성·김치 프리미엄·공포탐욕지수를 반영하고, 움직임이 작으면 원인은 2개로 간단히.
- 원인은 시장마다 3개 이상, 서로 다른 축(펀더멘털·정책/금리·수급/포지션·심리)에서 찾고, 웹 검색을 충분히 해서 근거를 확인하세요.
- 전망은 조건부 시나리오로 쓰고 확정적 예측은 하지 마세요.
- 확인된 사실(발표, 실적, 지표, 발언)과 시장의 해석을 구분해서 쓰세요. 해석은 '시장에서는 ~로 받아들였다'처럼 쓰세요.
- 주어진 시세 데이터와 맞지 않는 수치를 만들지 마세요. 확인 안 된 내용은 빼세요.
- 시장 이름은 '미국 증시'·'나스닥'·'한국 증시'·'코스피'처럼 정확하게. 매수·매도 권유 금지. 문체는 '~했다/~이다'.
- 출처 표시용 <cite> 태그는 넣지 말고, 출처는 sources에만 모으세요.
반드시 아래 형식의 JSON 객체 하나만 출력하세요. 설명 문장, 코드블록, 주석 금지.
{"title": "전체 분석 제목(35자 이내)",
 "summary": "전체 핵심 요약 2문장",
 "parts": [{"market": "us 또는 kr 또는 crypto", "title": "이 시장 분석 제목(30자 이내)", "summary": "2문장",
            "causes": [{"title": "원인(20자 이내)", "weight": "높음 또는 중간 또는 낮음", "detail": "근거가 되는 사건·수치와 영향 2~4문장"}],
            "reaction": "업종·종목별 반응 2~3문장",
            "outlook": {"stance": "상승 우위 또는 중립 또는 하락 우위", "horizon": "1~2주", "reason": "근거 2~3문장",
                        "scenarios": [{"name": "기본", "likelihood": "높음/중간/낮음", "direction": "up/flat/down", "desc": "조건과 흐름"}, {"name": "상방", "likelihood": "", "desc": ""}, {"name": "하방", "likelihood": "", "desc": ""}],
                        "levels": ["볼 만한 지수 수준 1~3개 (technicals 근거)"]}}],
 "link": "미국 증시와 한국 증시가 서로 미치는 영향 경로 2문장",
 "history": "과거 비슷한 급등락 사례와 이후 흐름 2~3문장 (검색으로 확인된 것만, 없으면 빈 문자열)",
 "watch": ["앞으로 확인할 변수 3~4개, 날짜가 있으면 함께"],
 "sources": [{"title": "기사 제목", "url": "https://..."}]}"""


def scen_direction(x: dict) -> str:
    d = str(x.get("direction", "")).lower()
    if d in ("up", "flat", "down"):
        return d
    name, desc = str(x.get("name", "")), str(x.get("desc", ""))
    if "상방" in name:
        return "up"
    if "하방" in name:
        return "down"
    if re.search(r"반등|상승|회복", desc) and not re.search(r"하락|약세|투매|이탈", desc):
        return "up"
    if re.search(r"하락|약세|투매|이탈|붕괴", desc) and not re.search(r"반등|회복", desc):
        return "down"
    return "flat"


def clean_outlook(o) -> dict | None:
    if not isinstance(o, dict) or not o.get("stance"):
        return None
    stance = str(o["stance"])
    stance = "상승 우위" if "상승" in stance else "하락 우위" if "하락" in stance else "중립"
    return {"stance": stance, "horizon": str(o.get("horizon", ""))[:20], "reason": CITE_RE.sub("", str(o.get("reason", "")))[:500],
            "scenarios": [{"name": str(x.get("name", ""))[:6], "likelihood": str(x.get("likelihood", ""))[:4],
                           "direction": scen_direction(x),
                           "desc": CITE_RE.sub("", str(x.get("desc", "")))[:300]} for x in (o.get("scenarios") or [])[:3] if x.get("desc")],
            "levels": [str(x)[:80] for x in (o.get("levels") or [])[:3]]}


ANALYSIS_BTC_MOVE = 5.0  # 비트코인 ±5% 이상


def analysis_triggers(indices: list[dict], crypto: dict | None = None) -> dict:
    """크게 움직인 지표를 시장별로: us(나스닥·나스닥100·VIX), kr(코스피·코스닥), crypto(비트코인)"""
    by = {i["symbol"]: i for i in indices}
    out = {"us": [], "kr": [], "crypto": []}
    btc = next((c for c in (crypto or {}).get("coins", []) if c["symbol"] == "BTC"), None)
    if btc and abs(btc["pct"]) >= ANALYSIS_BTC_MOVE:
        out["crypto"].append(f"비트코인 {btc['pct']:+.2f}%")
    for mk, syms in (("us", ("^IXIC", "^NDX")), ("kr", ("^KS11", "^KQ11"))):
        for sym in syms:
            i = by.get(sym)
            if i and abs(i["pct"]) >= ANALYSIS_INDEX_MOVE:
                out[mk].append(f"{i['name']} {i['pct']:+.2f}%")
    vix = by.get("^VIX")
    if vix and vix["pct"] >= ANALYSIS_VIX_JUMP:
        out["us"].append(f"VIX {vix['pct']:+.1f}%")
    return out


def todays_analysis(date: str) -> tuple[dict | None, str | None]:
    """오늘 이미 쓴 심층 분석과, 그 분석을 처음 쓴 브리핑(key)을 돌려준다 (하루 한 번 제한)"""
    found = []
    for ses in ("morning", "afternoon"):
        key = f"{date}-{ses}"
        try:
            a = json.loads((ARCHIVE_DIR / f"{key}.json").read_text("utf-8")).get("analysis")
        except Exception:  # noqa: BLE001
            continue
        if a:
            found.append((a, key))
    for a, key in found:  # 원본(다른 데서 빌려오지 않은 것) 우선
        if a.get("origin") == key or (not a.get("origin") and not a.get("reused")):
            return a, key
    if found:  # 예전 버그로 모두 '빌려온 분석'으로 표시된 경우: 기록된 원본, 없으면 그 파일을 원본으로
        a, key = found[0]
        return a, a.get("origin") or key
    return None, None


def market_key(m) -> str:
    m = str(m or "").lower()
    return "crypto" if m.startswith(("crypto", "coin", "코인", "btc")) else "kr" if m.startswith(("k", "한")) else "us"


def write_analysis(payload: dict, trig: dict) -> dict | None:
    triggers = trig["us"] + trig["kr"] + trig["crypto"]
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    from anthropic import Anthropic
    try:
        msg = Anthropic().messages.create(
            model=DEEP_MODEL,
            max_tokens=8000,
            system=ANALYSIS_SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
            messages=[{"role": "user", "content":
                       f"triggers: {json.dumps(trig, ensure_ascii=False)}\n왜 이렇게 움직였는지 시장별로 분석해 주세요.\n시세·뉴스 데이터:\n"
                       + json.dumps(payload, ensure_ascii=False)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = parse_json_loose(text[text.find('{"title"'):] if '{"title"' in text else text)
    except Exception as e:  # noqa: BLE001
        print(f"[analysis] 실패: {e}")
        return None
    parts_in = [x for x in (data or {}).get("parts", []) if isinstance(x, dict) and x.get("causes")]
    if not parts_in and (data or {}).get("causes"):  # 예전 형식으로 답한 경우
        parts_in = [dict(data, market="kr" if trig["kr"] and not trig["us"] else "us")]
    if not parts_in:
        print("[analysis] 분석 결과를 받지 못했습니다")
        return None
    def clean_causes(cs):
        return [{"title": str(c.get("title", ""))[:40], "weight": str(c.get("weight", "중간"))[:4],
                 "detail": CITE_RE.sub("", str(c.get("detail", "")))[:600]} for c in (cs or [])[:5] if c.get("title")]

    clean = {
        "triggers": triggers,
        "trig": trig,
        "title": str(data.get("title", ""))[:60],
        "summary": CITE_RE.sub("", str(data.get("summary", "")))[:400],
        "parts": [{"market": market_key(x.get("market")),
                   "title": str(x.get("title", ""))[:50],
                   "summary": CITE_RE.sub("", str(x.get("summary", "")))[:400],
                   "causes": clean_causes(x.get("causes")),
                   "reaction": CITE_RE.sub("", str(x.get("reaction", "")))[:500],
                   "outlook": clean_outlook(x.get("outlook"))} for x in parts_in[:3]],
        "link": CITE_RE.sub("", str(data.get("link", "")))[:400],
        "history": CITE_RE.sub("", str(data.get("history", "")))[:500],
        "watch": [CITE_RE.sub("", str(o))[:120] for o in (data.get("watch") or [])[:4]],
        "sources": [{"title": str(x.get("title", ""))[:100], "url": x["url"]} for x in data.get("sources", [])[:8]
                    if str(x.get("url", "")).startswith("http")],
    }
    order = {"us": 0, "kr": 1, "crypto": 2}
    clean["parts"].sort(key=lambda x: order.get(x["market"], 9))  # 미국 → 한국 → 코인
    print(f"[analysis] {clean['title']} (시장 {[x['market'] for x in clean['parts']]}, 출처 {len(clean['sources'])}개)")
    return clean


CAL_REFRESH_DAYS = 30  # 달력 일정 다시 검색하는 간격(일): 각 달은 "다음 달"일 때와 "이번 달"일 때 두 번 확인됨
CAL_SYSTEM = """당신은 한국 개인투자자를 위한 경제 일정 편집자입니다.
웹 검색으로 확인된 공식 일정만 넣고, 확인되지 않은 날짜는 넣지 마세요. 추측 금지.
시간은 한국시간(KST) 24시간제 "HH:MM"으로, 모르면 빈 문자열.
반드시 아래 형식의 JSON 객체 하나만 출력하세요. 설명 문장, 코드블록, 주석 금지.
{"events": [{"date": "YYYY-MM-DD", "time": "21:30", "country": "us 또는 kr", "title": "짧은 일정명", "short": "달력 칸용 2~6글자 약칭(예: CPI, 고용, FOMC, 금통위, 엔비디아)", "importance": 1~3 숫자(3=시장 영향 큼), "note": "한 줄 설명(선택)"}]}"""

CAL_PROMPT = """{month} 한 달 동안의 주요 경제 일정을 찾아 정리해 주세요.
포함할 것:
- 미국: FOMC 회의·의사록, 소비자물가(CPI), 생산자물가(PPI), 고용보고서, 개인소비지출(PCE), GDP, 소매판매, ISM·S&P글로벌 PMI, 미시간대·콘퍼런스보드 소비자심리, 주택지표, 주요 빅테크 실적 발표, 옵션 만기일
- 한국: 한국은행 금융통화위원회, 수출입 동향, 소비자물가, 선물옵션 동시만기일, 주요 대형주 실적 발표
importance 3은 FOMC 금리 결정, CPI, 고용보고서, PCE, 금통위처럼 시장을 크게 움직이는 일정에만 주세요.
미국 발표는 한국시간으로 바꿔서 적어 주세요(서머타임 반영)."""


def build_calendar() -> list[dict]:
    """이번 달·다음 달 일정을 한 달에 한 번 Claude 웹 검색으로 갱신 → docs/data/calendar.json"""
    path = DATA_DIR / "calendar.json"
    cal = json.loads(path.read_text("utf-8")) if path.exists() else {"updated": {}, "events": []}
    now = dt.datetime.now(KST)
    first_next = (now.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    months = [now.strftime("%Y-%m"), first_next.strftime("%Y-%m")]

    if os.getenv("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        client = Anthropic()
        for month in months:
            last = cal["updated"].get(month)
            if last and (now - dt.datetime.fromisoformat(last)).days < CAL_REFRESH_DAYS:
                continue
            try:
                msg = client.messages.create(
                    model=DEEP_MODEL,
                    max_tokens=8000,
                    system=CAL_SYSTEM,
                    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
                    messages=[{"role": "user", "content": CAL_PROMPT.format(month=month)}],
                )
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                data = parse_json_loose(text[text.find('{"events"'):] if '{"events"' in text else text)
                events = [e for e in (data or {}).get("events", [])
                          if str(e.get("date", "")).startswith(month) and e.get("title")]
                if not events:
                    print(f"[calendar] {month}: 일정을 받지 못해 기존 데이터 유지")
                    continue
                cal["events"] = [e for e in cal["events"] if not e["date"].startswith(month)] + [
                    {"date": e["date"], "time": str(e.get("time", ""))[:5], "country": e.get("country", "us"),
                     "title": str(e["title"])[:40], "short": str(e.get("short", ""))[:8], "importance": int(e.get("importance", 1) or 1),
                     "note": str(e.get("note", ""))[:80]} for e in events]
                cal["updated"][month] = now.isoformat(timespec="minutes")
                print(f"[calendar] {month}: {len(events)}건 갱신")
            except Exception as e:  # noqa: BLE001
                print(f"[calendar] {month} 실패: {e}")

    # 석 달 지난 일정은 정리
    cutoff = (now.replace(day=1) - dt.timedelta(days=95)).strftime("%Y-%m")
    cal["events"] = sorted([e for e in cal["events"] if e["date"][:7] >= cutoff],
                           key=lambda e: (e["date"], e.get("time") or "99:99"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal, ensure_ascii=False, indent=1), "utf-8")
    return cal["events"]


# ── 저장 ─────────────────────────────────────────────────────────
def repair_index(index: list[dict]) -> None:
    """예전 버그로 '심층 분석' 표시가 빠진 날을 보관 파일을 보고 바로잡는다"""
    by_date: dict[str, list[dict]] = {}
    for e in index:
        by_date.setdefault(e["date"], []).append(e)
    for date, entries in by_date.items():
        docs = {}
        for e in entries:
            try:
                a = json.loads((ARCHIVE_DIR / f"{e['key']}.json").read_text("utf-8")).get("analysis")
            except Exception:  # noqa: BLE001
                a = None
            docs[e["key"]] = a
        with_a = [k for k, a in docs.items() if a]
        if not with_a:
            continue
        orig = next((k for k in with_a if docs[k].get("origin") == k
                     or (not docs[k].get("origin") and not docs[k].get("reused"))), None)
        orig = orig or docs[with_a[0]].get("origin") or with_a[0]
        for e in entries:
            is_orig = e["key"] == orig
            if bool(e.get("analysis")) != is_orig:
                print(f"[archive] {e['key']}: 심층 분석 표시 {'복구' if is_orig else '정리'}")
            e["analysis"] = is_orig
            if is_orig and docs.get(e["key"]):
                e["analysis_title"] = docs[e["key"]].get("title")
                e["analysis_triggers"] = docs[e["key"]].get("triggers")


def save(doc: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(doc, ensure_ascii=False, indent=1)
    (DATA_DIR / "latest.json").write_text(blob, encoding="utf-8")

    key = doc.get("key") or f"{doc['date']}-{doc['session']}"
    (ARCHIVE_DIR / f"{key}.json").write_text(blob, encoding="utf-8")

    index_path = ARCHIVE_DIR / "index.json"
    index = json.loads(index_path.read_text("utf-8")) if index_path.exists() else []
    def pct_of(sym):
        return next((i["pct"] for i in doc["indices"] if i["symbol"] == sym), None)

    # 아카이브 검색용: 그날 크게 움직인 종목 이름도 함께 저장
    movers = sorted(doc["stocks"]["us"] + doc["stocks"]["kr"], key=lambda s: -abs(s["pct"]))
    entry = {
        "key": key, "date": doc["date"], "session": doc["session"], "time": doc["generated_at"][11:16],
        "headline": doc["headline"], "tags": doc.get("tags", []),
        "us_pct": pct_of("^IXIC"), "kr_pct": pct_of("^KS11"),
        "summary": " ".join(doc["commentary"].values())[:300],
        "keywords": [s["name"] for s in movers[:4]] + ([doc["analysis"]["title"]] if doc.get("analysis") else []),
        "analysis": bool(doc.get("analysis")) and not doc["analysis"].get("reused"),
        "analysis_title": (doc.get("analysis") or {}).get("title") if doc.get("analysis") and not doc["analysis"].get("reused") else None,
        "analysis_triggers": (doc.get("analysis") or {}).get("triggers") if doc.get("analysis") and not doc["analysis"].get("reused") else None,
        "stance": ((((doc.get("analysis") or {}).get("parts") or [{}])[0].get("outlook"))
                   or doc.get("outlook") or {}).get("stance"),
    }
    index = [e for e in index if e["key"] != key]
    index.insert(0, entry)
    default_time = {"morning": "07:10", "afternoon": "15:50"}
    index.sort(key=lambda e: (e["date"], e.get("time") or default_time.get(e["session"], "12:00")), reverse=True)
    repair_index(index)
    index_path.write_text(json.dumps(index[:500], ensure_ascii=False, indent=1), "utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    et = now.astimezone(ZoneInfo("America/New_York"))
    kr_open = now.weekday() < 5 and dt.time(9, 0) <= now.time() < dt.time(15, 30)
    us_open = et.weekday() < 5 and dt.time(9, 30) <= et.time() < dt.time(16, 0)
    if manual and (kr_open or us_open):
        session = "intraday"  # 직접 실행했는데 장이 열려 있으면 장중 브리핑 (마감 브리핑과 따로 저장)
    else:
        session = "morning" if now.hour < 12 else "afternoon"  # 오전=미국 증시 마감, 오후=한국 증시 마감
    print(f"[session] {session} (직접 실행={manual}, 한국장 열림={kr_open}, 미국장 열림={us_open})")

    prev = load_previous()
    indices = fetch_quotes(INDICES)
    stocks = {}
    for mk, pool in (("us", US_POOL), ("kr", KR_POOL), ("kq", KOSDAQ_POOL)):
        top, caps = top_by_market_cap(pool)
        rows = fetch_quotes(top)
        for rank, r in enumerate(sorted(rows, key=lambda r: -caps.get(r["symbol"], 0)), 1):
            r["cap"] = caps.get(r["symbol"])
            r["rank"] = rank
        stocks[mk] = sorted(rows, key=lambda r: r["rank"])
    sectors = {"us": fetch_quotes(US_SECTORS), "kr": fetch_quotes(KR_SECTORS)}
    # 한국 지수가 한국 종목보다 날짜가 늦으면 네이버로 보정, 그다음 이전 브리핑보다 뒤로 가지 않게
    fix_kr_indices(indices, [r["date"] for k in ("kr", "kq") for r in stocks.get(k, [])]
                   + [r["date"] for r in sectors.get("kr", [])])
    indices = no_regress(indices, prev.get("indices"), "지수")
    for k in stocks:
        stocks[k] = no_regress(stocks[k], (prev.get("stocks") or {}).get(k), f"종목({k})")
    for k in sectors:
        sectors[k] = no_regress(sectors[k], (prev.get("sectors") or {}).get(k), f"섹터({k})")
    macro = no_regress(fetch_quotes(MACRO), prev.get("macro"), "매크로")
    usdkrw = next((m["price"] for m in macro if m["symbol"] == "KRW=X"), None)
    try:
        etfs = fetch_etfs()
    except Exception as e:  # noqa: BLE001
        print(f"[etf] 실패: {e}")
        etfs = {}
    try:
        crypto = fetch_crypto(usdkrw)
    except Exception as e:  # noqa: BLE001
        print(f"[crypto] 실패: {e}")
        crypto = None
    if kr3y := fetch_ecos_kr3y():
        macro.insert(3, kr3y)
    news = fetch_news()
    movers = {}  # 상승·하락 상위 목록은 사용하지 않음 (fetch_movers()로 다시 켤 수 있음)

    for job in (build_seasonality, build_calendar):
        try:
            job()
        except Exception as e:  # noqa: BLE001
            print(f"[{job.__name__}] 실패: {e}")
    upcoming = []
    try:
        cal = json.loads((DATA_DIR / "calendar.json").read_text("utf-8"))
        today, week = now.strftime("%Y-%m-%d"), (now + dt.timedelta(days=7)).strftime("%Y-%m-%d")
        upcoming = [e for e in cal["events"] if today <= e["date"] <= week]
    except Exception:  # noqa: BLE001
        pass

    # 토큰 절약: Claude에는 스파크라인을 빼고 전달
    def lite(rows):
        return [{k: v for k, v in r.items() if k != "spark"} for r in rows]

    payload = {
        "now_kst": now.strftime("%Y-%m-%d %H:%M"),
        "session": (f"장중 ({now:%H:%M} 기준, 열려 있는 시장: {', '.join(x for x, o in (('한국 증시', kr_open), ('미국 증시', us_open)) if o)})"
                    if session == "intraday" else "미국 증시 마감 직후" if session == "morning" else "한국 증시 마감 직후"),
        "indices": lite(indices),
        "stocks": {k: lite(v) for k, v in stocks.items()},
        "sectors": {k: lite(v) for k, v in sectors.items()},
        "macro": lite(macro),
        "news": [{"i": n, "market": x["market"], "title": x["title"]} for n, x in enumerate(news)],
        "upcoming_events": upcoming,  # watch 항목 작성에 참고
        "technicals": technicals(indices),  # 전망·지수 수준 근거
        "crypto": {"coins": [{k: v for k, v in c.items() if k != "spark"} for c in crypto["coins"]],
                   "fear_greed": crypto["fng"]} if crypto else None,
    }
    brief = write_with_claude(payload) or fallback_briefing(indices)
    analysis = None
    trig = analysis_triggers(indices, crypto)
    key_now = f"{now.strftime('%Y-%m-%d')}-{session}"
    earlier, origin = todays_analysis(now.strftime("%Y-%m-%d"))

    def shown(a: dict) -> dict:
        """같은 브리핑에서 쓴 분석이면 원본 그대로, 다른 브리핑(아침→오후)에서 가져오면 reused 표시"""
        a = dict(a, origin=origin)
        if origin == key_now:
            a.pop("reused", None)
        else:
            a["reused"] = True
        return a

    has_crypto = any(x.get("market") == "crypto" for x in (earlier or {}).get("parts", []))
    if session == "intraday":
        analysis = shown(earlier) if earlier else None  # 장중 브리핑은 심층 분석을 새로 쓰지 않음
    elif earlier and earlier.get("parts") and not (manual and crypto and not has_crypto):
        # 하루 한 번: 오늘 이미 쓴 분석은 그대로 보여줌
        analysis = shown(earlier)
        print(f"[analysis] 오늘 이미 쓴 심층 분석을 다시 보여줍니다 (처음 쓴 브리핑: {origin})")
    elif trig["us"] or trig["kr"] or trig["crypto"]:
        if session == "morning" or manual:
            print(f"[analysis] 큰 변동: {trig} → 심층 분석 작성")
            analysis = write_analysis(payload, trig)
            if analysis:
                analysis["origin"] = key_now
        else:
            print(f"[analysis] 큰 변동: {trig} → 심층 분석은 다음 날 아침 브리핑에서 작성합니다")
    if analysis is None and earlier:
        analysis = shown(earlier)  # 새로 쓰기에 실패하면 오늘 쓴 분석이라도 보여줌

    ko = brief.get("ko_names") or {}
    for d in ("up", "down"):
        for r in movers.get("us", {}).get(d, []):
            if isinstance(ko.get(r["symbol"]), str) and ko[r["symbol"]].strip():
                r["name_en"], r["name"] = r["name"], ko[r["symbol"]].strip()[:20]

    notes = {n["i"]: n["note"] for n in brief.get("news_notes", []) if "i" in n}
    for n, item in enumerate(news):
        if n in notes:
            item["note"] = notes[n]

    doc = {
        "generated_at": now.isoformat(timespec="minutes"),
        "date": now.strftime("%Y-%m-%d"),
        "session": session,
        "key": f"{now:%Y-%m-%d}-intraday-{now:%H%M}" if session == "intraday" else f"{now:%Y-%m-%d}-{session}",
        "intraday": {"at": f"{now:%H:%M}",
                     "kr": kr_open and any(i["symbol"] == "^KS11" and i["date"] == now.strftime("%Y-%m-%d") for i in indices),
                     "us": us_open and any(i["symbol"] == "^IXIC" and i["date"] == et.strftime("%Y-%m-%d") for i in indices)}
                    if session == "intraday" else None,
        "sample": False,
        "headline": brief.get("headline", ""),
        "commentary": {k: brief.get(k, "") for k in ("us", "kr", "macro", "crypto")},
        "crypto": crypto,
        "etfs": etfs,
        "watch": brief.get("watch", []),
        "tags": [t.lstrip("#").strip() for t in brief.get("tags", []) if t.strip()][:5],
        "indices": indices, "stocks": stocks, "sectors": sectors, "macro": macro, "movers": movers,
        "news": news,
        "analysis": analysis,
        "drivers": [str(x)[:200] for x in (brief.get("drivers") or [])[:3]],
        "outlook": clean_outlook(brief.get("outlook")),
    }
    save(doc)
    print(f"저장 완료: {doc['date']} {session} / {doc['headline']}")


if __name__ == "__main__":
    main()
