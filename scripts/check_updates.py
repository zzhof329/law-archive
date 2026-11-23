"""
국가법령정보센터 현행 법령 페이지에서 시행일·공포일·공포번호를 읽어
data/status.json, data/status.js 를 갱신합니다. (GitHub Actions에서 매일 실행)
- API 키 불필요. 법령 페이지의 숨은 입력값(lsiSeq, ancYd, ancNo, frm_efYd)을 읽습니다.
- 이전 결과와 버전번호(lsiSeq)가 다르면 '개정 감지'로 기록합니다.
- 접속에 실패한 법령은 이전 값을 그대로 둡니다.
"""
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SOURCES = ["items.js", "items_extra.js", "manual.js"]
EXTRA = os.path.join(DATA, "extra_laws.txt")
JSON_FILE = os.path.join(DATA, "status.json")
JS_FILE = os.path.join(DATA, "status.js")
KST = datetime.timezone(datetime.timedelta(hours=9))


def collect_laws():
    laws = {}
    for name in SOURCES:
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        for m in re.finditer(r'law:"([^"]+)"\s*,\s*jo:"[^"]*"(?:\s*,\s*kind:"([^"]+)")?', src):
            laws.setdefault(m.group(1), m.group(2) or "법령")
        q = re.search(r"QUICK_LAWS\s*=\s*\[([\s\S]*?)\]", src)
        if q:
            for m in re.finditer(r'"([^"]+)"', q.group(1)):
                laws.setdefault(m.group(1), "법령")
    if os.path.exists(EXTRA):
        with open(EXTRA, encoding="utf-8") as f:
            for line in f:
                n = line.strip()
                if not n or n.startswith("#"):
                    continue
                kind = "법령"
                if n.startswith("행정규칙:"):
                    kind, n = "행정규칙", n[len("행정규칙:"):].strip()
                laws.setdefault(n, kind)
    return laws


def hidden(page, id_):
    m = re.search(r'<input[^>]*id="' + re.escape(id_) + r'"[^>]*value="([^"]*)"', page)
    return m.group(1) if m else ""


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; law-archive-checker/1.0)",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def norm(s):
    return re.sub(r"[\sㆍ·]", "", s or "")


def main():
    now = datetime.datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    prev = {}
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
    prev_laws = prev.get("laws") or {}
    history = list(prev.get("history") or [])

    laws = collect_laws()
    out, changed, failed = {}, 0, 0
    print(f"법령 {len(laws)}건 개정 확인 시작")
    for i, (name, kind) in enumerate(laws.items(), 1):
        url = "https://www.law.go.kr/" + urllib.parse.quote(kind) + "/" + urllib.parse.quote(name)
        rec = {"kind": kind, "ok": False, "title": "", "lsiSeq": "", "ancYd": "", "ancNo": "",
               "efYd": "", "anc": "", "changedOn": "", "checkedOn": today}
        old = prev_laws.get(name)
        try:
            page = fetch(url)
            t = re.search(r"<title>\s*([^<]*?)\s*&gt;", page)
            rec["title"] = html.unescape(t.group(1)).strip() if t else ""
            if kind == "행정규칙":
                rec["lsiSeq"] = hidden(page, "admRulSeq") or hidden(page, "admRulId")
                rec["ancYd"] = hidden(page, "prmlYd")
                rec["ancNo"] = hidden(page, "prmlNo")
                rec["efYd"] = hidden(page, "efYd")
            else:
                rec["lsiSeq"] = hidden(page, "lsiSeq")
                rec["ancYd"] = hidden(page, "ancYd")
                rec["ancNo"] = hidden(page, "ancNo")
                rec["efYd"] = hidden(page, "frm_efYd")
            a = re.search(r"\[\s*([^\[\]<>]{2,40}?제\s*[\d\-]+\s*호\s*,[^\[\]<>]{4,40}?)\s*\]", page)
            if a:
                rec["anc"] = re.sub(r"\s+", " ", a.group(1)).strip()
            rec["ok"] = bool(rec["lsiSeq"]) and norm(rec["title"]) == norm(name)
        except Exception as e:  # noqa: BLE001
            rec["title"] = "접속 실패: " + str(e)[:120]

        if old:
            rec["changedOn"] = old.get("changedOn", "")
        tag = ""
        if rec["ok"] and old and old.get("ok") and old.get("lsiSeq") and old["lsiSeq"] != rec["lsiSeq"]:
            rec["changedOn"] = today
            history.insert(0, {"date": today, "law": name,
                               "fromAncYd": old.get("ancYd", ""), "fromEfYd": old.get("efYd", ""),
                               "toAncYd": rec["ancYd"], "toEfYd": rec["efYd"],
                               "ancNo": rec["ancNo"], "anc": rec["anc"]})
            changed += 1
            tag = "  ★ 개정 감지"
        if not rec["ok"]:
            failed += 1
            if old and old.get("ok"):
                for k in ("lsiSeq", "ancYd", "ancNo", "efYd", "anc"):
                    rec[k] = old.get(k, "")
                rec["ok"] = True
                rec["stale"] = True
            print(f"[{i}/{len(laws)}] {name} → 확인 실패 ({rec['title']})")
        else:
            print(f"[{i}/{len(laws)}] {name} 시행 {rec['efYd']} / 공포 {rec['ancYd']}{tag}")
        out[name] = rec
        time.sleep(0.4)

    if laws and failed == len(laws):
        print("모든 법령 확인에 실패했습니다. 기존 파일을 그대로 둡니다.")
        sys.exit(1)

    result = {"checkedAt": now.strftime("%Y-%m-%d %H:%M"), "laws": out, "history": history[:300]}
    text = json.dumps(result, ensure_ascii=False, indent=1)
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("window.LAW_STATUS = " + text + ";\n")
    print(f"완료: {len(laws)}건 확인, 개정 감지 {changed}건, 실패 {failed}건")


if __name__ == "__main__":
    main()
