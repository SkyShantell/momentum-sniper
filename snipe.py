#!/usr/bin/env python3
"""Momentum Academy — Kalodata Sniper (student kit, advanced route).

Runs YOUR Kalodata presets through a cloud browser and writes a vetted
product CSV next to this file. Same engine Momentum uses for the Weekly Drop.

One-time setup (see SNIPE-SOP.md):
  1. Save the 4 Momentum presets in YOUR Kalodata (exact names: HighTicket, Lurkers, Hardcore, 100 GAP)
  2. Create .env next to this file:
       KALODATA_EMAIL=you@email.com
       KALODATA_PASSWORD=yourpassword
       FIRECRAWL_API_KEY=fc-...        (free key from firecrawl.dev)
  3. python3 snipe.py                  (or: python3 snipe.py HighTicket)
"""
import csv, datetime, json, pathlib, re, sys, time, urllib.request, urllib.error, urllib.parse

BASE = pathlib.Path(__file__).parent
# Momentum's proven presets (exact filter values are in the app → Resources → Automate
# Your Product Research). You can also pass ANY preset name you saved in your own Kalodata.
MOMENTUM_PRESETS = ["HighTicket", "Lurkers", "Hardcore", "100 GAP"]
VET_TOP = 12
RESTRICTED = ["crocs", "ninja", "shark", "liquid iv", "liquid i.v"]
TRUSTED = ["qvc"]

CAPTIONS = [
    "I am so sorry if you already grabbed an [PRODUCT], because the discount is huge today. 😱😭",
    "This is your sign to finally grab the [PRODUCT]. 😱😭",
    "Do NOT scroll past the [PRODUCT] if it has been sitting in your cart. 😱😭",
    "POV: you found the [PRODUCT] before everyone else did. 😱😭",
    "If you have been waiting on the [PRODUCT], now is the time. 😱😭",
    "Run, do not walk, to grab the [PRODUCT]. 😱😭",
    "The [PRODUCT] everyone has been asking me about is finally back. 😱😭",
    "Stop overthinking the [PRODUCT] and just tap the cart. 😱😭",
    "Me telling you to grab the [PRODUCT] before it sells out again. 😱😭",
    "Your future self will thank you for grabbing the [PRODUCT] today. 😱😭",
    "Adding the [PRODUCT] to my cart before I change my mind. 😱😭",
    "The [PRODUCT] is about to be everywhere. Get it first. 😱😭",
    "I can not believe how good the [PRODUCT] is for the price. 😱😭",
    "Consider this your reminder to grab the [PRODUCT] you keep eyeing. 😱😭",
    "Trust me, you want the [PRODUCT] in your cart today. 😱😭",
]

def env():
    e = {}
    f = BASE / ".env"
    if not f.exists():
        sys.exit("Missing .env — see SNIPE-SOP.md step 2")
    for line in open(f):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            e[k.strip()] = v.strip().strip("'").strip('"')
    for k in ("KALODATA_EMAIL", "KALODATA_PASSWORD", "FIRECRAWL_API_KEY"):
        if not e.get(k): sys.exit(f"Missing {k} in .env")
    return e

ENV = None

def log(m): print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

def fc(actions, label):
    payload = {"url": "https://www.kalodata.com/login", "formats": ["markdown"], "actions": actions}
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://api.firecrawl.dev/v2/scrape", method="POST",
                headers={"Authorization": f"Bearer {ENV['FIRECRAWL_API_KEY']}",
                         "Content-Type": "application/json"},
                data=json.dumps(payload).encode())
            r = json.loads(urllib.request.urlopen(req, timeout=280).read())
            vals = [x.get("value") for x in r.get("data", {}).get("actions", {}).get("javascriptReturns", [])]
            # Find the login-status return (the JSON blob carrying a "logined" key),
            # NOT vals[0] which is the 'go' button-click return.
            ok = False
            for v in vals:
                if isinstance(v, str) and '"logined"' in v:
                    try:
                        st = json.loads(v)
                        ok = (st.get("logined") == "true") or ("/login" not in str(st.get("url", "")))
                    except Exception:
                        ok = False
                    break
            if not ok: raise RuntimeError("login wall / not authenticated")
            return vals
        except Exception as e:
            last = e
            log(f"  retry {attempt+1}/3 {label}: {str(e)[:100]}")
            time.sleep(25)
    raise SystemExit(f"{label} failed after 3 tries: {last}")

def login_actions():
    return [
        {"type": "wait", "milliseconds": 5000},
        {"type": "click", "selector": 'input[placeholder="Email"]'},
        {"type": "write", "text": ENV["KALODATA_EMAIL"]},
        {"type": "wait", "milliseconds": 600},
        {"type": "click", "selector": 'input[placeholder="Password"]'},
        {"type": "write", "text": ENV["KALODATA_PASSWORD"]},
        {"type": "wait", "milliseconds": 600},
        {"type": "executeJavascript", "script": "(()=>{const b=[...document.querySelectorAll('button')].find(b=>/log ?in/i.test(b.innerText));if(b)b.click();return 'go'})()"},
        {"type": "wait", "milliseconds": 15000},
        {"type": "executeJavascript", "script": "JSON.stringify({url:location.href, logined:localStorage.getItem('logined')})"},
    ]

ROWS_JS = r"""JSON.stringify((()=>{
  const head=[...document.querySelectorAll('thead th')].map(th=>th.innerText.trim());
  const rows=[...document.querySelectorAll('tbody tr')].filter(r=>r.querySelectorAll('td').length>3);
  // The product cover + id both live in a CSS background-image whose URL contains
  // .../tiktok.product/<id>/cover.png (Kalodata's shadcn table has no <img> or <a> in rows).
  const findCover=(r)=>{
    for(const e of r.querySelectorAll('*')){
      let bg='';
      try{bg=getComputedStyle(e).backgroundImage||'';}catch(_){}
      const m=bg.match(/tiktok\.product\/(\d+)\//);
      if(m){const um=bg.match(/url\(["']?([^"')]+)["']?\)/); return {id:m[1], img:um?um[1]:null};}
    }
    return {id:null, img:null};
  };
  return {head, rows: rows.map(r => {
    const cov=findCover(r);
    return {id: cov.id, img: cov.img, cells: [...r.querySelectorAll('td')].map(td => td.innerText.trim())};
  })};
})())"""

def num(s):
    if not s: return None
    s = str(s).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.match(r"^>?(-?[\d.]+)(k|m)?$", s, re.I)
    if not m: return None
    v = float(m.group(1))
    if m.group(2): v *= 1000 if m.group(2).lower() == "k" else 1_000_000
    return v

def pull(preset):
    # Presets render as <button>…<div class="truncate">HighTicket</div>…</button>. The click
    # handler lives on the BUTTON — clicking just the inner label does NOT apply the filter
    # (you get Kalodata's default top-by-revenue list). So match the clean-text label, then
    # click it AND climb its ancestors so the button's handler fires and the filter applies.
    # (The /product page takes ~15-20s to paint the tabs, so we wait before a single click.)
    click_js = ("(()=>{const want=%s.replace(/\\s+/g,'');"
                "const norm=t=>((t.textContent||'').replace(/\\s+/g,''));"
                "const lab=[...document.querySelectorAll('div.truncate,[role=tab],button,a,li')].find(t=>norm(t)===want);"
                "if(!lab)return 'missing';"
                "let el=lab;for(let i=0;i<4&&el;i++){el.click();el=el.parentElement;}"
                "return 'clicked';})()") % json.dumps(preset)
    acts = login_actions() + [
        {"type": "executeJavascript", "script": "location.assign('https://www.kalodata.com/product')"},
        {"type": "wait", "milliseconds": 16000},
        # ONE click only — the preset button is a toggle, so a second click deselects it and
        # you fall back to Kalodata's default top-by-revenue list. 16s is enough paint time.
        {"type": "executeJavascript", "script": click_js},
        {"type": "wait", "milliseconds": 8000},
        # Bump page size 10 -> 50 (shadcn "N/Page" combobox) so one read covers the batch.
        {"type": "executeJavascript", "script": "(()=>{const b=[...document.querySelectorAll('[role=combobox]')].find(e=>/\\/\\s*page/i.test(e.textContent||''));if(b){b.click();return 'opened'}return 'nocombo'})()"},
        {"type": "wait", "milliseconds": 1500},
        {"type": "executeJavascript", "script": "(()=>{const o=[...document.querySelectorAll('[role=option],[role=menuitem]')].find(e=>/^50(\\/page)?$/i.test((e.textContent||'').replace(/\\s+/g,'')));if(o){o.click();return 'set50'}return 'no50'})()"},
        {"type": "wait", "milliseconds": 6000},
        {"type": "executeJavascript", "script": ROWS_JS},
    ]
    vals = fc(acts, f"pull:{preset}")
    data = None
    for v in vals:
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                obj = json.loads(v)
            except Exception:
                continue
            if isinstance(obj, dict) and "rows" in obj:
                data = obj
                break
    if not data or not data.get("rows"):
        return []
    head = data.get("head", [])

    def col(*keys, exclude=()):
        for i, h in enumerate(head):
            hl = h.lower()
            if any(k in hl for k in keys) and not any(x in hl for x in exclude):
                return i
        return None

    ci = {
        "name": col("product", "title"),
        "rev": col("revenue", exclude=("growth", "trend", "live", "video", "card")),
        "grow": col("growth"),
        "price": col("avg", "unit price"),
        "comm": col("commission"),
        "creat": col("creator count", "creator"),
        "conv": col("conversion", "cvr"),
    }

    def cell(c, key):
        i = ci[key]
        return c[i] if (i is not None and i < len(c)) else None

    out = []
    for row in data["rows"]:
        c = row.get("cells", [])
        if len(c) < 4: continue
        raw = cell(c, "name") or (c[1] if len(c) > 1 else "")
        name = raw.split("\n")[0].strip()          # first line is the product title; drop price/icon lines
        name = re.sub(r"^\d+\s+", "", name)          # drop a leading rank number if it bled into the name cell
        out.append({"id": row.get("id"), "img": row.get("img"), "name": name[:160],
                    "revenue": num(cell(c, "rev")), "growth": num(cell(c, "grow")),
                    "avg_price": num(cell(c, "price")), "commission": num(cell(c, "comm")),
                    "creators": num(cell(c, "creat")), "conv": num(cell(c, "conv"))})
    return [p for p in out if p["revenue"] is not None]

def detail_url(pid):
    today = datetime.date.today()
    dr = urllib.parse.quote(json.dumps([str(today - datetime.timedelta(days=7)),
                                        str(today - datetime.timedelta(days=1))]))
    return (f"https://www.kalodata.com/product/detail?id={pid}"
            f"&language=en-US&currency=USD&region=US&dateRange={dr}&cateValue=%5B%5D")

DETAIL_JS = r"""JSON.stringify((()=>{
  const hasAD=r=>[...r.querySelectorAll('*')].some(e=>!e.children.length&&(e.textContent||'').trim()==='AD');
  // The video table is the shadcn <table> whose header row contains "Video Content".
  // Count how many of its top-10 rows carry an AD badge = ad momentum behind the product.
  let vt=null;
  for(const tbl of document.querySelectorAll('table')){
    const h=[...tbl.querySelectorAll('thead th')].map(th=>th.innerText||'').join(' ');
    if(/Video Content/.test(h)){vt=tbl;break;}
  }
  let ads=null;
  if(vt){const rows=[...vt.querySelectorAll('tbody tr')].slice(0,10); ads=rows.filter(hasAD).length;}
  // Shop/seller name — best effort (the redesign hides it; the ad-check is the real gate).
  let shop=null;
  const cand=[...document.querySelectorAll('a[href*="/shop/"],a[href*="seller"],a[href*="store"]')]
    .map(a=>(a.textContent||'').trim()).filter(t=>t&&!/view on tiktok/i.test(t));
  if(cand[0]) shop=cand[0];
  // Product images: collect ALL tiktok.product covers on the page (gallery + cover)
  // so the app can vision-pick the human-free product-only shot. img = first found.
  let img=null;const imgs=[];
  try{
    for(const e of document.querySelectorAll('*')){let bg='';try{bg=getComputedStyle(e).backgroundImage||''}catch(_){}
      const m=bg.match(/url\(["']?([^"')]*tiktok\.product[^"')]+)["']?\)/); if(m&&!imgs.includes(m[1])){imgs.push(m[1]); if(imgs.length>=8)break;}}
    if(imgs.length)img=imgs[0];
    if(!img){const els=[...document.querySelectorAll('img')].filter(e=>e.naturalWidth>=120&&(e.src||'').startsWith('http'));
      const pick=els.find(e=>/tiktokcdn|p16-oec|kalocdn|byteimg/i.test(e.src))||els.sort((a,b)=>b.naturalWidth*b.naturalHeight-a.naturalWidth*a.naturalHeight)[0]; img=pick?pick.src:null;}
  }catch(e){}
  const conv=((document.body.innerText.match(/Creator Conversion Rate\s*([\d.]+)%/)||[])[1])||null;
  return {shop, ads, img, imgs, conv};
})())"""

def vet(cands):
    kept = []
    detail_signal = False   # did the detail-page scrape return ANY real ad/shop data?
    for i in range(0, len(cands), 3):
        chunk = cands[i:i+3]
        acts = login_actions()
        for p in chunk:
            acts += [
                {"type": "executeJavascript", "script": f"location.assign('{detail_url(p['id'])}')"},
                {"type": "wait", "milliseconds": 7000},
                {"type": "executeJavascript",
                 "script": "(()=>{const h=[...document.querySelectorAll('*')].find(e=>!e.children.length&&(e.textContent||'').trim()==='Video Content');if(h){h.scrollIntoView();return 's'}window.scrollTo(0,document.body.scrollHeight);return 'b'})()"},
                {"type": "wait", "milliseconds": 5000},
                {"type": "executeJavascript", "script": DETAIL_JS},
            ]
        vals = fc(acts, f"vet:{i//3+1}")
        details = []
        for v in vals:
            if isinstance(v, str) and v.startswith("{"):
                try: d = json.loads(v)
                except Exception: continue
                if "ads" in d or "shop" in d: details.append(d)
        for p, d in zip(chunk, details):
            shop = (d.get("shop") or "").strip()
            ads_raw = d.get("ads")
            ads = int(ads_raw) if isinstance(ads_raw, (int, float)) else 0
            name_l = p["name"].lower()
            if not shop:
                brand_ok = True   # shop is hidden on the redesigned detail page; the ad-check is the gate
            else:
                brand_ok = (any(t in shop.lower() for t in TRUSTED)
                            or any(t in set(re.findall(r"[a-z]{3,}", shop.lower()))
                                   for t in re.findall(r"[a-z]{3,}", name_l)[:6])
                            or not any(b in name_l for b in ["dyson","apple","stanley","elf","tarte","medicube","goli","lemme","nike","adidas"]))
            p["shop"], p["ads"] = shop, ads
            if d.get("img"):
                p["img"] = d.get("img")   # detail-page image is best; keep the row image otherwise
            # Alternate shots of THIS product only (the detail page also shows related products).
            alts = [u for u in (d.get("imgs") or []) if isinstance(u, str) and f"tiktok.product/{p['id']}/" in u]
            if alts:
                p["detail_imgs"] = alts
            if isinstance(ads_raw, (int, float)):
                detail_signal = True      # the video table was found & counted (even if 0 ads)
            if brand_ok and ads >= 5:
                kept.append(p)
                log(f"  KEEP {p['name'][:48]} | {shop or 'shop?'} | ads {ads}/10")
            else:
                log(f"  cut  {p['name'][:48]} | shop={shop!r} ads={ads}")
        time.sleep(10)
    if not kept and cands and not detail_signal:
        # The detail-page AD/shop check couldn't read anything (Kalodata redesigned the
        # detail page). Rather than return nothing, pass the pulled products through
        # un-vetted so the run still produces a CSV + images. Review ADs before rendering.
        log(f"  ⚠ AD-vetting unavailable (detail pages returned nothing) — passing top "
            f"{min(len(cands),10)} products through UN-VETTED. Eyeball the ADs before you render.")
        for p in cands:
            p.setdefault("shop", "")
            p["ads"] = None
        return cands[:10]
    return kept

def og_image(pid):
    """The public TikTok Shop page's og:image — a free extra image candidate,
    often a cleaner product-only studio shot than the Kalodata cover."""
    try:
        req = urllib.request.Request(f"https://shop.tiktok.com/view/product/{pid}", headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        m = re.search(r'property="og:image" content="([^"]+)"', html)
        return m.group(1).replace("&amp;", "&") if m else None
    except Exception:
        return None

def caption(pid, name):
    clean = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", name)
    short = re.split(r"[,.(\[|]", clean)[0].strip()[:48] or "product"
    idx = abs(hash(str(pid))) % len(CAPTIONS)   # pid may be non-numeric now; hash is stable per run
    return CAPTIONS[idx].replace("[PRODUCT]", short)

SCENE_PROMPT = "put the product from the image on a clean modern surface that fits the product, natural lighting"

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40] or "product"

def download_image(url, dest):
    """Save a product image locally so it can be dragged straight into the
    AI Director's Bulk Factory. TikTok/Kalodata CDNs serve these publicly."""
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.kalodata.com/",
        })
        data = urllib.request.urlopen(req, timeout=30).read()
        if len(data) < 1000:
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        log(f"  image download failed: {str(e)[:80]}")
        return False

def push_to_director(product, img_path):
    """Optional (Phase 3): if the student pasted their AI Director ingest key
    into .env, push the product straight into their Director inbox so it's
    queued in Bulk Factory with no files to drag. No key = silently skipped."""
    key = ENV.get("DIRECTOR_INGEST_KEY")
    if not key:
        return False
    url = ENV.get("DIRECTOR_INGEST_URL", "https://app.momentumacademy.co/api/director/ingest")
    payload = {"product_name": product["name"], "caption": product.get("caption", ""),
               "scene_prompt": product.get("scene_prompt", SCENE_PROMPT),
               "meta": {"image_candidates": product.get("image_candidates") or [],
                        "price": product.get("avg_price"), "revenue": product.get("revenue"),
                        "growth": product.get("growth"), "commission": product.get("commission"),
                        "per_sale": product.get("per_sale"), "creators": product.get("creators"),
                        "ads": product.get("ads"), "shop": product.get("shop"),
                        "link": f"https://shop.tiktok.com/view/product/{product['id']}"}}
    if img_path and img_path.exists():
        import base64
        payload["image_base64"] = "data:image/jpeg;base64," + base64.b64encode(img_path.read_bytes()).decode()
    elif product.get("img"):
        payload["image_url"] = product["img"]
    else:
        return False
    try:
        req = urllib.request.Request(url, method="POST",
            headers={"Content-Type": "application/json", "x-ingest-key": key},
            data=json.dumps(payload).encode())
        urllib.request.urlopen(req, timeout=60).read()
        return True
    except Exception as e:
        log(f"  director push failed for {product['name'][:40]}: {str(e)[:80]}")
        return False

def main():
    global ENV
    ENV = env()
    preset = sys.argv[1] if len(sys.argv) > 1 else "HighTicket"
    # Any preset name works: a Momentum preset OR one you saved yourself in Kalodata.
    if preset not in MOMENTUM_PRESETS:
        log(f"(custom preset '{preset}' — using your own saved Kalodata filter. Momentum presets: {MOMENTUM_PRESETS})")
    log(f"sniping preset: {preset}")
    pool = pull(preset)
    log(f"pulled {len(pool)} products")
    keep = []
    for p in pool:
        if any(b in p["name"].lower() for b in RESTRICTED): continue
        if (p["revenue"] or 0) < 15000: continue
        price = p["avg_price"] or 0
        if price < 8 or price * (p["commission"] or 0) / 100 < 1.25: continue
        keep.append(p)
    keep.sort(key=lambda x: (-(x["avg_price"] or 0 >= 50), -(x["revenue"] or 0)))
    # The AD-icon + shop safety check is MANDATORY and runs by default: it opens each
    # product's detail page and counts how many of its top videos are running ads (7+ = strong,
    # under 5 = cut). This is what keeps your TikTok account alive. Do not skip it.
    if ENV.get("SKIP_VET") == "1":
        log(f"SKIP_VET=1 set — passing top {min(VET_TOP, len(keep))} through WITHOUT the AD safety check (review them yourself!)")
        final = keep[:VET_TOP]
        for p in final:
            p.setdefault("shop", "")
            p["ads"] = None
    else:
        log(f"{len(keep)} pass filters, vetting top {min(VET_TOP, len(keep))}")
        final = vet(keep[:VET_TOP])
    # Image candidates per winner: Kalodata cover + detail-page alternates + the
    # TikTok Shop og:image. The app vision-picks the human-free product-only shot.
    for p in final:
        cands = []
        for u in [p.get("img")] + list(p.get("detail_imgs") or []):
            if u and u not in cands:
                cands.append(u)
        og = og_image(p.get("id")) if p.get("id") else None
        if og and og not in cands:
            cands.append(og)
        p["image_candidates"] = cands[:6]
    imgdir = BASE / "sniped-products"
    imgdir.mkdir(exist_ok=True)
    run_stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = BASE / f"snipe-{preset.replace(' ','')}-{run_stamp}.csv"
    saved, pushed = 0, 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # image_file/image_url lead so the AI Director import can match each row
        # to its downloaded photo. Drag the sniped-products folder into Bulk
        # Factory and drop this CSV on top; names + captions fill themselves in.
        w.writerow(["product", "image_file", "image_url", "image_candidates_json",
                    "avg_price", "revenue_7d", "growth_pct", "commission_pct",
                    "per_sale_$", "creators", "ads_top10", "shop", "tiktok_link",
                    "caption", "scene_prompt"])
        for p in final:
            p["caption"] = caption(p["id"], p["name"])
            p["scene_prompt"] = SCENE_PROMPT
            per_sale = round((p["avg_price"] or 0) * (p["commission"] or 0) / 100, 2)
            p["per_sale"] = per_sale
            fname = f"{slug(p['name'])}-{p['id']}.jpg"
            got = download_image(p.get("img"), imgdir / fname)
            if got:
                saved += 1
            w.writerow([p["name"], fname if got else "", p.get("img") or "",
                        json.dumps(p.get("image_candidates") or [], ensure_ascii=False),
                        p["avg_price"], p["revenue"], p["growth"], p["commission"],
                        per_sale, p["creators"], p["ads"],
                        p["shop"], f"https://shop.tiktok.com/view/product/{p['id']}",
                        p["caption"], p["scene_prompt"]])
            if push_to_director(p, (imgdir / fname) if got else None):
                pushed += 1
    log(f"DONE — {len(final)} vetted products -> {out.name}")
    log(f"images -> {imgdir.name}/ ({saved}/{len(final)} downloaded)")
    if pushed:
        log(f"pushed {pushed} straight to your AI Director inbox")

if __name__ == "__main__":
    main()
