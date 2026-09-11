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
import csv, datetime, hashlib, json, pathlib, re, sys, time, urllib.request, urllib.error, urllib.parse

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

CREATOR_ROWS_JS = r"""JSON.stringify((()=>{
  const tables=[...document.querySelectorAll('table')];
  const table=tables.find(t=>/creator/i.test((t.querySelector('thead')?.innerText||''))) || tables[0];
  if(!table) return {head:[],rows:[],error:'creator-table-missing',url:location.href};

  const head=[...table.querySelectorAll('thead th')].map(th=>(th.innerText||th.textContent||'').trim());
  const rows=[...table.querySelectorAll('tbody tr')].filter(r=>r.querySelectorAll('td').length>2);

  const bgImage=(r)=>{
    for(const e of r.querySelectorAll('*')){
      try{
        const bg=getComputedStyle(e).backgroundImage||'';
        const m=bg.match(/url\(["']?([^"')]+)["']?\)/);
        if(m && m[1] && !m[1].startsWith('data:')) return m[1];
      }catch(_){}
    }
    return '';
  };

  return {
    head,
    url: location.href,
    rows: rows.map(r=>{
      const links=[...r.querySelectorAll('a[href]')].map(a=>({
        href:a.href||'',
        text:(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim()
      }));
      const creatorLink=
        links.find(x=>/\/creator\/detail/i.test(x.href)) ||
        links.find(x=>/\/creator/i.test(x.href) && !/\/creator\/?$/.test(x.href));
      const idMatch=(creatorLink?.href||'').match(/[?&]id=(\d+)/);
      const img=r.querySelector('img[src]')?.src || bgImage(r) || '';
      return {
        id:idMatch?idMatch[1]:'',
        link:creatorLink?.href||'',
        link_text:creatorLink?.text||'',
        img,
        cells:[...r.querySelectorAll('td')].map(td=>(td.innerText||td.textContent||'').trim())
      };
    })
  };
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


def _saved_filter_click_js(preset):
    """Click one saved Kalodata custom filter by its exact visible name."""
    return ("(()=>{const want=%s.replace(/\\s+/g,'');"
            "const norm=t=>((t.textContent||'').replace(/\\s+/g,''));"
            "const lab=[...document.querySelectorAll('div.truncate,[role=tab],button,a,li')].find(t=>norm(t)===want);"
            "if(!lab)return 'preset-missing';"
            "let el=lab;for(let i=0;i<4&&el;i++){el.click();el=el.parentElement;}"
            "return 'preset-clicked';})()") % json.dumps(preset)


def _creator_header_key(text, index):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return f"column_{index+1}"
    key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return key or f"column_{index+1}"


def pull_creators(preset):
    """Open Kalodata Creator, apply a saved custom filter, and scrape up to 50 visible creators."""
    click_js = _saved_filter_click_js(preset)
    acts = login_actions() + [
        # Direct navigation is the browser equivalent of clicking the Creator top tab,
        # and is less fragile than relying on the nav label DOM.
        {"type": "executeJavascript", "script": "location.assign('https://www.kalodata.com/creator')"},
        {"type": "wait", "milliseconds": 16000},
        {"type": "executeJavascript", "script": click_js},
        {"type": "wait", "milliseconds": 8000},
        # Match Product mode: expand the creator table to 50 rows.
        {"type": "executeJavascript", "script": "(()=>{const b=[...document.querySelectorAll('[role=combobox]')].find(e=>/\\/\\s*page/i.test(e.textContent||''));if(b){b.click();return 'page-opened'}return 'page-combo-missing'})()"},
        {"type": "wait", "milliseconds": 1500},
        {"type": "executeJavascript", "script": "(()=>{const o=[...document.querySelectorAll('[role=option],[role=menuitem]')].find(e=>/^50(\\/page)?$/i.test((e.textContent||'').replace(/\\s+/g,'')));if(o){o.click();return 'page-set50'}return 'page-50-missing'})()"},
        {"type": "wait", "milliseconds": 6000},
        {"type": "executeJavascript", "script": CREATOR_ROWS_JS},
    ]
    vals = fc(acts, f"creator:{preset}")

    for v in vals:
        if isinstance(v, str) and v.startswith(("preset-", "page-")):
            log(f"  Creator page: {v}")

    data = None
    for v in vals:
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                obj = json.loads(v)
            except Exception:
                continue
            if isinstance(obj, dict) and "rows" in obj and "head" in obj:
                data = obj
                break

    if not data:
        return [], []
    rows = data.get("rows") or []
    head = data.get("head") or []
    if not rows:
        return [], head

    # Make stable unique CSV keys from whatever columns Kalodata currently renders.
    keys = []
    used = {}
    for i, h in enumerate(head):
        base = _creator_header_key(h, i)
        used[base] = used.get(base, 0) + 1
        keys.append(base if used[base] == 1 else f"{base}_{used[base]}")

    creator_idx = None
    for i, h in enumerate(head):
        hl = str(h or "").lower()
        if "creator" in hl and "count" not in hl:
            creator_idx = i
            break

    out = []
    for row in rows:
        cells = list(row.get("cells") or [])
        raw = ""
        if creator_idx is not None and creator_idx < len(cells):
            raw = str(cells[creator_idx] or "")
        if not raw:
            raw = str(row.get("link_text") or "")
        if not raw:
            raw = next((str(x) for x in cells if str(x).strip()), "")

        lines = [re.sub(r"\s+", " ", x).strip() for x in raw.splitlines() if x.strip()]
        handle = next((x for x in lines if x.startswith("@")), "")
        creator_name = next(
            (x for x in lines if not x.startswith("@") and not re.fullmatch(r"\d+", x)),
            handle or (lines[0] if lines else "")
        )
        if not handle:
            link_text = str(row.get("link_text") or "").strip()
            if link_text.startswith("@"):
                handle = link_text

        rec = {
            "creator": creator_name[:200],
            "handle": handle[:120],
            "creator_id": str(row.get("id") or ""),
            "creator_url": str(row.get("link") or ""),
            "profile_image": str(row.get("img") or ""),
        }
        for i, key in enumerate(keys):
            if i < len(cells):
                value = str(cells[i] or "").strip()
                if value:
                    rec[key] = value
        out.append(rec)

    return out, head


def write_creator_csv(preset, creators):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_preset = re.sub(r"[^A-Za-z0-9_-]+", "", preset.replace(" ", "")) or "Custom"
    out = BASE / f"snipe-creator-{safe_preset}-{stamp}.csv"

    preferred = ["creator", "handle", "creator_id", "creator_url", "profile_image"]
    dynamic = []
    for row in creators:
        for key in row.keys():
            if key not in preferred and key not in dynamic:
                dynamic.append(key)
    fields = preferred + dynamic

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in creators:
            w.writerow({k: row.get(k, "") for k in fields})
    return out



TOP_CREATOR_META_JS = r"""JSON.stringify((()=>{
  const tables=[...document.querySelectorAll('table')];
  const table=tables.find(t=>{
    const h=(t.querySelector('thead')?.innerText||'').toLowerCase();
    return h.includes('creator') && h.includes('revenue') && h.includes('item sold');
  }) || tables[0];
  if(!table)return {error:'creator-table-missing'};

  const head=[...table.querySelectorAll('thead th')].map(th=>(th.innerText||th.textContent||'').trim());
  const row=table.querySelector('tbody tr');
  if(!row)return {error:'top-creator-row-missing',head};

  const cells=[...row.querySelectorAll('td')].map(td=>(td.innerText||td.textContent||'').trim());
  const allText=(row.innerText||row.textContent||'').replace(/\s+/g,' ').trim();
  const handle=(allText.match(/@[A-Za-z0-9._-]+/)||[])[0]||'';
  const link=[...row.querySelectorAll('a[href]')]
    .map(a=>a.href||'')
    .find(h=>/\/creator\/detail/i.test(h))||'';
  const idMatch=link.match(/[?&]id=(\d+)/);

  let image='';
  const im=row.querySelector('img[src]');
  if(im)image=im.src||'';

  return {head,cells,handle,link,creator_id:idMatch?idMatch[1]:'',image};
})())"""

CLICK_TOP_CREATOR_JS = r"""(()=>{
  const tables=[...document.querySelectorAll('table')];
  const table=tables.find(t=>{
    const h=(t.querySelector('thead')?.innerText||'').toLowerCase();
    return h.includes('creator') && h.includes('revenue') && h.includes('item sold');
  }) || tables[0];
  if(!table)return 'top-creator-table-missing';
  const row=table.querySelector('tbody tr');
  if(!row)return 'top-creator-row-missing';

  const a=[...row.querySelectorAll('a[href]')].find(a=>/\/creator\/detail/i.test(a.href||''));
  if(a){a.click();return 'top-creator-clicked-link';}

  const handleLeaf=[...row.querySelectorAll('*')].find(e=>!e.children.length && /^@[A-Za-z0-9._-]+$/.test((e.textContent||'').trim()));
  if(handleLeaf){
    let el=handleLeaf;
    for(let i=0;i<4 && el;i++){
      try{el.click();}catch(_){}
      el=el.parentElement;
    }
    return 'top-creator-clicked-handle';
  }

  try{row.click();return 'top-creator-clicked-row';}catch(_){}
  return 'top-creator-click-failed';
})()"""

CLICK_CREATOR_PRODUCT_JS = r"""(()=>{
  // Creator detail has a left-side "Product" section. Avoid the global top nav
  // by preferring an exact Product label lower on the page and toward the left.
  const leaves=[...document.querySelectorAll('*')].filter(e=>
    !e.children.length && (e.textContent||'').trim()==='Product'
  );
  let target=leaves.find(e=>{
    const r=e.getBoundingClientRect();
    return r.top>120 && r.left<window.innerWidth*0.45;
  });
  if(!target)target=leaves.find(e=>e.getBoundingClientRect().top>120);
  if(!target)return 'creator-product-tab-missing';

  const clicker=target.closest('button,a,[role="tab"],[role="button"],li')||target;
  try{clicker.click();}catch(_){try{target.click();}catch(__){}}
  try{target.scrollIntoView({block:'center'});}catch(_){}
  return 'creator-product-tab-clicked';
})()"""

SCROLL_CREATOR_PRODUCT_TABLE_JS = r"""(()=>{
  const tables=[...document.querySelectorAll('table')];
  const table=tables.find(t=>{
    const h=(t.querySelector('thead')?.innerText||'').toLowerCase();
    return h.includes('product') && h.includes('revenue') && h.includes('item sold') && h.includes('avg');
  });
  if(!table)return 'creator-product-table-missing';
  table.scrollIntoView({block:'center'});
  return 'creator-product-table-ready';
})()"""

CREATOR_PRODUCTS_JS = r"""JSON.stringify((()=>{
  const tables=[...document.querySelectorAll('table')];
  const table=tables.find(t=>{
    const h=(t.querySelector('thead')?.innerText||'').toLowerCase();
    return h.includes('product') && h.includes('revenue') && h.includes('item sold') && h.includes('avg');
  });
  if(!table)return {head:[],rows:[],error:'creator-product-table-missing'};

  const head=[...table.querySelectorAll('thead th')].map(th=>(th.innerText||th.textContent||'').trim());
  const rows=[...table.querySelectorAll('tbody tr')].slice(0,10);

  const cover=(r)=>{
    for(const e of r.querySelectorAll('*')){
      let bg='';
      try{bg=getComputedStyle(e).backgroundImage||'';}catch(_){}
      const idm=bg.match(/tiktok\.product\/(\d+)\//);
      if(idm){
        const um=bg.match(/url\(["']?([^"')]+)["']?\)/);
        return {id:idm[1],img:um?um[1]:''};
      }
    }
    const a=[...r.querySelectorAll('a[href]')].find(a=>/\/product\/detail/i.test(a.href||''));
    const m=(a?.href||'').match(/[?&]id=(\d+)/);
    const im=r.querySelector('img[src]');
    return {id:m?m[1]:'',img:im?.src||''};
  };

  return {
    head,
    rows:rows.map(r=>{
      const c=cover(r);
      const a=[...r.querySelectorAll('a[href]')].find(a=>/\/product\/detail/i.test(a.href||''));
      return {
        id:c.id,
        img:c.img,
        detail_url:a?.href||'',
        cells:[...r.querySelectorAll('td')].map(td=>(td.innerText||td.textContent||'').trim())
      };
    })
  };
})())"""

CREATOR_PRODUCT_DETAIL_JS = r"""JSON.stringify((()=>{
  const hasAD=r=>[...r.querySelectorAll('*')].some(e=>!e.children.length&&(e.textContent||'').trim()==='AD');

  let vt=null;
  for(const tbl of document.querySelectorAll('table')){
    const h=[...tbl.querySelectorAll('thead th')].map(th=>th.innerText||'').join(' ');
    if(/Video Content/i.test(h)){vt=tbl;break;}
  }
  let ads=null;
  if(vt){
    const rows=[...vt.querySelectorAll('tbody tr')].slice(0,10);
    ads=rows.filter(hasAD).length;
  }

  const body=(document.body.innerText||'').replace(/\u00a0/g,' ');
  const commissionMatch=body.match(/Commission Rate\s*:?\s*([\d.]+)%/i);
  const priceMatch=body.match(/Price\s*:?\s*\$([\d,.]+)/i);
  const commission=commissionMatch?parseFloat(commissionMatch[1]):null;
  const listed_price=priceMatch?parseFloat(priceMatch[1].replace(/,/g,'')):null;

  let shop=null;
  const cand=[...document.querySelectorAll('a[href*="/shop/"],a[href*="seller"],a[href*="store"]')]
    .map(a=>(a.textContent||'').trim()).filter(t=>t&&!/view on tiktok/i.test(t));
  if(cand[0])shop=cand[0];

  let img=null;const imgs=[];
  try{
    for(const e of document.querySelectorAll('*')){
      let bg='';try{bg=getComputedStyle(e).backgroundImage||''}catch(_){}
      const m=bg.match(/url\(["']?([^"')]*tiktok\.product[^"')]+)["']?\)/);
      if(m&&!imgs.includes(m[1])){imgs.push(m[1]);if(imgs.length>=8)break;}
    }
    if(imgs.length)img=imgs[0];
    if(!img){
      const els=[...document.querySelectorAll('img')].filter(e=>e.naturalWidth>=120&&(e.src||'').startsWith('http'));
      const pick=els.find(e=>/tiktokcdn|p16-oec|kalocdn|byteimg/i.test(e.src))||
        els.sort((a,b)=>b.naturalWidth*b.naturalHeight-a.naturalWidth*a.naturalHeight)[0];
      img=pick?pick.src:null;
    }
  }catch(_){}

  return {ads,commission,listed_price,shop,img,imgs};
})())"""



CREATOR_SEARCH_JS = r"""(()=>{
  const input=[...document.querySelectorAll('input')].find(i=>
    /search creator/i.test(i.getAttribute('placeholder')||'') ||
    /creator.*name.*handle/i.test(i.getAttribute('placeholder')||'')
  );
  if(!input)return 'creator-search-input-missing';

  const q=__QUERY__;
  const setter=Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,'value'
  )?.set;
  if(setter)setter.call(input,q);else input.value=q;

  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  input.focus();
  input.dispatchEvent(new KeyboardEvent('keydown',{
    key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true
  }));
  input.dispatchEvent(new KeyboardEvent('keypress',{
    key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true
  }));
  input.dispatchEvent(new KeyboardEvent('keyup',{
    key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true
  }));

  const form=input.closest('form');
  try{if(form)form.requestSubmit();}catch(_){}
  return 'creator-search-submitted:'+q;
})()"""


def _creator_record_to_target(rec, rank=None):
    """Normalize a Creator ranking/search row into the object used by product scanning."""
    revenue = rec.get("revenue")
    if revenue is None:
        # Be tolerant of Kalodata header variations such as Revenue($).
        for key, value in rec.items():
            kl = str(key).lower()
            if "revenue" in kl and "trend" not in kl:
                revenue = value
                break
    return {
        "handle": str(rec.get("handle") or ""),
        "name": str(rec.get("creator") or ""),
        "creator_id": str(rec.get("creator_id") or ""),
        "creator_page_url": str(rec.get("creator_url") or ""),
        "creator_revenue": num(revenue) if revenue not in (None, "") else None,
        "profile_image": str(rec.get("profile_image") or ""),
        "creator_rank": rank,
    }


def pull_ranked_creators(preset, count):
    """Return the top N creators from one saved Creator custom filter."""
    rows, headers = pull_creators(preset)
    targets = []
    for idx, rec in enumerate(rows, start=1):
        target = _creator_record_to_target(rec, rank=idx)
        if "/creator/detail" not in target["creator_page_url"]:
            continue
        targets.append(target)
        if len(targets) >= count:
            break

    if not targets:
        header_preview = " | ".join(str(x) for x in headers[:12])
        raise RuntimeError(
            "Kalodata Creator filter returned no usable creator detail links. "
            + (f"Headers seen: {header_preview}" if header_preview else "")
        )
    return targets


def find_creator_by_name(query):
    """Use Kalodata's Creator search box and return the first matching creator."""
    q = str(query or "").strip()
    if not q:
        raise RuntimeError("Enter a creator name or @handle.")

    script = CREATOR_SEARCH_JS.replace("__QUERY__", json.dumps(q))
    acts = login_actions() + [
        {"type": "executeJavascript", "script": "location.assign('https://www.kalodata.com/creator')"},
        {"type": "wait", "milliseconds": 16000},
        {"type": "executeJavascript", "script": script},
        {"type": "wait", "milliseconds": 8000},
        {"type": "executeJavascript", "script": CREATOR_ROWS_JS},
    ]
    vals = fc(acts, f"creator-search:{q}")

    for v in vals:
        if isinstance(v, str) and v.startswith("creator-search-"):
            log(f"  Creator search: {v}")

    data = None
    for v in vals:
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                obj = json.loads(v)
            except Exception:
                continue
            if isinstance(obj, dict) and "rows" in obj and "head" in obj:
                data = obj

    if not data or not data.get("rows"):
        raise RuntimeError(f"No Kalodata Creator results were returned for {q!r}.")

    # Reuse the same row parsing logic used by pull_creators(), but for the
    # already-filtered search result table.
    head = list(data.get("head") or [])
    keys = []
    used = {}
    for i, h in enumerate(head):
        base = _creator_header_key(h, i)
        used[base] = used.get(base, 0) + 1
        keys.append(base if used[base] == 1 else f"{base}_{used[base]}")

    creator_idx = None
    for i, h in enumerate(head):
        hl = str(h or "").lower()
        if "creator" in hl and "count" not in hl:
            creator_idx = i
            break

    candidates = []
    for row in data.get("rows") or []:
        cells = list(row.get("cells") or [])
        raw = ""
        if creator_idx is not None and creator_idx < len(cells):
            raw = str(cells[creator_idx] or "")
        if not raw:
            raw = str(row.get("link_text") or "")
        if not raw:
            raw = next((str(x) for x in cells if str(x).strip()), "")

        lines = [re.sub(r"\s+", " ", x).strip() for x in raw.splitlines() if x.strip()]
        handle = next((x for x in lines if x.startswith("@")), "")
        creator_name = next(
            (x for x in lines if not x.startswith("@") and not re.fullmatch(r"\d+", x)),
            handle or (lines[0] if lines else "")
        )
        if not handle:
            link_text = str(row.get("link_text") or "").strip()
            if link_text.startswith("@"):
                handle = link_text

        rec = {
            "creator": creator_name[:200],
            "handle": handle[:120],
            "creator_id": str(row.get("id") or ""),
            "creator_url": str(row.get("link") or ""),
            "profile_image": str(row.get("img") or ""),
        }
        for i, key in enumerate(keys):
            if i < len(cells):
                value = str(cells[i] or "").strip()
                if value:
                    rec[key] = value
        candidates.append(rec)

    if not candidates:
        raise RuntimeError(f"Kalodata returned rows for {q!r}, but no creator could be parsed.")

    norm_q = re.sub(r"[^a-z0-9]+", "", q.lower().lstrip("@"))

    def score(rec):
        h = re.sub(r"[^a-z0-9]+", "", str(rec.get("handle") or "").lower().lstrip("@"))
        n = re.sub(r"[^a-z0-9]+", "", str(rec.get("creator") or "").lower())
        if h == norm_q:
            return 100
        if n == norm_q:
            return 95
        if h.startswith(norm_q) or norm_q.startswith(h):
            return 80
        if norm_q and (norm_q in h or norm_q in n):
            return 60
        return 0

    candidates.sort(key=score, reverse=True)
    target = _creator_record_to_target(candidates[0], rank=None)
    if "/creator/detail" not in target["creator_page_url"]:
        raise RuntimeError(
            f"Found {target.get('handle') or target.get('name') or q}, "
            "but Kalodata did not expose a creator detail link."
        )
    return target



def pull_top_creator(preset):
    """Apply one saved Creator filter and click/open the #1 ranked creator."""
    click_js = _saved_filter_click_js(preset)
    acts = login_actions() + [
        {"type": "executeJavascript", "script": "location.assign('https://www.kalodata.com/creator')"},
        {"type": "wait", "milliseconds": 16000},
        {"type": "executeJavascript", "script": click_js},
        {"type": "wait", "milliseconds": 8000},
        {"type": "executeJavascript", "script": TOP_CREATOR_META_JS},
        {"type": "executeJavascript", "script": CLICK_TOP_CREATOR_JS},
        {"type": "wait", "milliseconds": 8000},
        {"type": "executeJavascript", "script": "JSON.stringify({creator_page_url:location.href})"},
    ]
    vals = fc(acts, f"creator-top:{preset}")

    meta = None
    creator_page_url = ""
    for v in vals:
        if isinstance(v, str) and v.startswith(("preset-", "top-creator-")):
            log(f"  Creator: {v}")
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                obj = json.loads(v)
            except Exception:
                continue
            if isinstance(obj, dict) and ("handle" in obj or "creator_id" in obj) and "cells" in obj:
                meta = obj
            if isinstance(obj, dict) and obj.get("creator_page_url"):
                creator_page_url = str(obj.get("creator_page_url") or "")

    if not meta:
        raise RuntimeError("Could not read the top creator from the saved Creator filter.")

    link = str(meta.get("link") or "")
    if "/creator/detail" not in creator_page_url and "/creator/detail" in link:
        creator_page_url = link
    if "/creator/detail" not in creator_page_url:
        raise RuntimeError(
            f"Top creator was found ({meta.get('handle') or 'unknown'}), but its detail page could not be opened."
        )

    # Best-effort creator name/revenue from the ranking row.
    cells = list(meta.get("cells") or [])
    head = list(meta.get("head") or [])
    creator_name = ""
    creator_revenue = None
    for i, h in enumerate(head):
        hl = str(h or "").lower()
        if "creator" in hl and i < len(cells):
            raw = str(cells[i] or "")
            lines = [x.strip() for x in raw.splitlines() if x.strip()]
            creator_name = next((x for x in lines if not x.startswith("@") and not x.isdigit()), "")
        if "revenue" in hl and "trend" not in hl and i < len(cells) and creator_revenue is None:
            creator_revenue = num(cells[i])

    return {
        "handle": str(meta.get("handle") or ""),
        "name": creator_name,
        "creator_id": str(meta.get("creator_id") or ""),
        "creator_page_url": creator_page_url,
        "creator_revenue": creator_revenue,
        "profile_image": str(meta.get("image") or ""),
    }


def pull_top_creator_products(creator):
    """Click the Product section on the creator detail page and read its top 10 products."""
    creator_url = str(creator.get("creator_page_url") or "")
    acts = login_actions() + [
        {"type": "executeJavascript", "script": f"location.assign({json.dumps(creator_url)})"},
        {"type": "wait", "milliseconds": 10000},
        {"type": "executeJavascript", "script": CLICK_CREATOR_PRODUCT_JS},
        {"type": "wait", "milliseconds": 3000},
        {"type": "executeJavascript", "script": SCROLL_CREATOR_PRODUCT_TABLE_JS},
        {"type": "wait", "milliseconds": 6000},
        {"type": "executeJavascript", "script": CREATOR_PRODUCTS_JS},
    ]
    vals = fc(acts, f"creator-products:{creator.get('handle') or creator.get('creator_id') or 'top'}")

    data = None
    for v in vals:
        if isinstance(v, str) and v.startswith(("creator-product-",)):
            log(f"  Creator products: {v}")
        if isinstance(v, str) and v.lstrip().startswith("{"):
            try:
                obj = json.loads(v)
            except Exception:
                continue
            if isinstance(obj, dict) and "rows" in obj and "head" in obj:
                data = obj

    if not data or not data.get("rows"):
        raise RuntimeError("The creator Product section opened, but no product rows could be read.")

    head = list(data.get("head") or [])

    def col(*keys, exclude=()):
        for i, h in enumerate(head):
            hl = str(h or "").lower()
            if any(k in hl for k in keys) and not any(x in hl for x in exclude):
                return i
        return None

    ci = {
        "name": col("product"),
        "rev": col("revenue", exclude=("trend", "live", "video", "card")),
        "sold": col("item sold"),
        "price": col("avg", "unit price"),
    }

    def cell(c, key):
        i = ci[key]
        return c[i] if (i is not None and i < len(c)) else None

    out = []
    for row in data.get("rows") or []:
        c = list(row.get("cells") or [])
        pid = str(row.get("id") or "")
        if not pid:
            continue
        raw = cell(c, "name") or (c[1] if len(c) > 1 else "")
        name = str(raw or "").splitlines()[0].strip()
        name = re.sub(r"^\d+\s+", "", name)
        if not name:
            name = f"Product {pid}"
        out.append({
            "id": pid,
            "img": row.get("img") or None,
            "name": name[:160],
            "revenue": num(cell(c, "rev")),
            "item_sold": num(cell(c, "sold")),
            "avg_price": num(cell(c, "price")),
            "growth": None,
            "commission": None,
            "creators": None,
            "conv": None,
            "source_creator": creator.get("handle") or "",
            "source_creator_name": creator.get("name") or "",
            "source_creator_revenue": creator.get("creator_revenue"),
            "source_creator_rank": creator.get("creator_rank"),
        })
    return out


def vet_creator_products(cands):
    """Strictly vet products found through a creator.

    Requirements mirror the normal Sniper:
      - avg price >= $8
      - commission earned per sale >= $3
      - at least 7 of top 10 videos are ads
      - restricted-name / brand-safety rules still apply
    """
    kept = []
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
                {"type": "executeJavascript", "script": CREATOR_PRODUCT_DETAIL_JS},
            ]

        vals = fc(acts, f"creator-vet:{i//3+1}")
        details = []
        for v in vals:
            if isinstance(v, str) and v.startswith("{"):
                try:
                    d = json.loads(v)
                except Exception:
                    continue
                if isinstance(d, dict) and ("ads" in d or "commission" in d):
                    details.append(d)

        for p, d in zip(chunk, details):
            ads_raw = d.get("ads")
            commission_raw = d.get("commission")
            ads = int(ads_raw) if isinstance(ads_raw, (int, float)) else None
            commission = float(commission_raw) if isinstance(commission_raw, (int, float)) else None
            price = p.get("avg_price")
            if not isinstance(price, (int, float)) or price <= 0:
                lp = d.get("listed_price")
                price = float(lp) if isinstance(lp, (int, float)) else 0.0

            p["avg_price"] = price
            p["commission"] = commission
            p["ads"] = ads
            p["shop"] = str(d.get("shop") or "").strip()
            p["per_sale"] = round(price * commission / 100, 2) if commission is not None else None

            if d.get("img"):
                p["img"] = d.get("img")
            alts = [
                u for u in (d.get("imgs") or [])
                if isinstance(u, str) and f"tiktok.product/{p['id']}/" in u
            ]
            if alts:
                p["detail_imgs"] = alts

            name_l = p["name"].lower()
            if any(b in name_l for b in RESTRICTED):
                log(f"  cut  {p['name'][:48]} | restricted name")
                continue

            shop = p["shop"]
            if not shop:
                brand_ok = True
            else:
                brand_ok = (
                    any(t in shop.lower() for t in TRUSTED)
                    or any(
                        t in set(re.findall(r"[a-z]{3,}", shop.lower()))
                        for t in re.findall(r"[a-z]{3,}", name_l)[:6]
                    )
                    or not any(
                        b in name_l
                        for b in ["dyson","apple","stanley","elf","tarte","medicube","goli","lemme","nike","adidas"]
                    )
                )

            if price < 8:
                log(f"  cut  {p['name'][:48]} | avg ${price:.2f} < $8")
                continue
            if commission is None:
                log(f"  cut  {p['name'][:48]} | commission unreadable")
                continue
            if p["per_sale"] < 3.00:
                log(f"  cut  {p['name'][:48]} | ${p['per_sale']:.2f}/sale < $3")
                continue
            if ads is None:
                log(f"  cut  {p['name'][:48]} | ad count unreadable")
                continue
            if ads < 7:
                log(f"  cut  {p['name'][:48]} | ads {ads}/10")
                continue
            if not brand_ok:
                log(f"  cut  {p['name'][:48]} | shop={shop!r} brand safety")
                continue

            kept.append(p)
            log(
                f"  KEEP {p['name'][:48]} | {p.get('source_creator') or 'creator'} "
                f"| ${price:.2f} | ${p['per_sale']:.2f}/sale | ads {ads}/10"
            )

        time.sleep(10)

    return kept


def write_creator_product_results(preset, creator, final):
    """Write creator-sourced winners in the same product format as normal Sniper results."""
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

    handle = re.sub(r"[^A-Za-z0-9_-]+", "", str(creator.get("handle") or "creator").lstrip("@")) or "creator"
    preset_safe = re.sub(r"[^A-Za-z0-9_-]+", "", preset.replace(" ", "")) or "Custom"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = BASE / f"snipe-creator-products-{handle}-{preset_safe}-{stamp}.csv"

    saved, pushed = 0, 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "product", "image_file", "image_url", "avg_price", "revenue_7d", "growth_pct",
            "commission_pct", "per_sale_$", "creators", "ads_top10", "shop", "tiktok_link",
            "source_creator", "source_creator_name", "source_creator_revenue", "source_creator_rank",
            "source_creators_all", "creator_item_sold", "caption", "scene_prompt"
        ])
        for p in final:
            p["caption"] = caption(p["id"], p["name"])
            p["scene_prompt"] = SCENE_PROMPT
            fname = f"{slug(p['name'])}-{p['id']}.jpg"
            got = download_image(p.get("img"), imgdir / fname)
            if got:
                saved += 1

            w.writerow([
                p["name"], fname if got else "", p.get("img") or "",
                p.get("avg_price"), p.get("revenue"), p.get("growth"),
                p.get("commission"), p.get("per_sale"), p.get("creators"), p.get("ads"),
                p.get("shop"), f"https://shop.tiktok.com/view/product/{p['id']}",
                p.get("source_creator"), p.get("source_creator_name"), p.get("source_creator_revenue"), p.get("source_creator_rank"),
                p.get("source_creators_all") or p.get("source_creator") or "",
                p.get("item_sold"), p["caption"], p["scene_prompt"]
            ])

            if push_to_director(p, (imgdir / fname) if got else None):
                pushed += 1

    return out, imgdir, saved, pushed


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
            if brand_ok and ads >= 7:
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
    mode = (sys.argv[2] if len(sys.argv) > 2 else "product").strip().lower()
    creator_source = (sys.argv[3] if len(sys.argv) > 3 else "filter").strip().lower()
    try:
        creator_count = max(1, min(10, int(sys.argv[4]))) if len(sys.argv) > 4 else 1
    except Exception:
        creator_count = 1
    creator_query = (sys.argv[5] if len(sys.argv) > 5 else "").strip()

    if mode == "creator":
        if creator_source == "name":
            creator = find_creator_by_name(creator_query or preset)
            creators_to_scan = [creator]
            scan_label = creator_query or creator.get("handle") or creator.get("name") or preset
            log(
                f"specific creator: {creator.get('handle') or creator.get('name') or creator.get('creator_id')} "
                f"| revenue {creator.get('creator_revenue') if creator.get('creator_revenue') is not None else '?'}"
            )
        else:
            log(f"creator-product scan preset: {preset} | checking top {creator_count} creator(s)")
            creators_to_scan = pull_ranked_creators(preset, creator_count)
            scan_label = f"top{len(creators_to_scan)}"
            log(
                "creators selected: "
                + ", ".join(
                    f"#{c.get('creator_rank')} {c.get('handle') or c.get('name') or c.get('creator_id')}"
                    for c in creators_to_scan
                )
            )

        all_final = []
        total_products = 0
        total_eligible = 0

        for creator_index, creator in enumerate(creators_to_scan, start=1):
            creator_label = creator.get("handle") or creator.get("name") or creator.get("creator_id") or f"creator-{creator_index}"
            rank_text = f"#{creator.get('creator_rank')} " if creator.get("creator_rank") else ""
            log(f"[{creator_index}/{len(creators_to_scan)}] scanning {rank_text}{creator_label}")

            pool = pull_top_creator_products(creator)
            total_products += len(pool)
            log(f"  pulled {len(pool)} products from {creator_label}'s Product section")

            eligible = [
                p for p in pool
                if not any(b in p["name"].lower() for b in RESTRICTED)
                and (p.get("avg_price") or 0) >= 8
            ]
            total_eligible += len(eligible)
            log(
                f"  {len(eligible)} pass the pre-check — vetting ALL for "
                "$3+/sale + 7/10 ads"
            )
            creator_final = vet_creator_products(eligible)
            all_final.extend(creator_final)
            log(f"  {len(creator_final)}/{len(pool)} passed for {creator_label}")

        # Do not send the same TikTok product twice if multiple successful creators
        # are promoting it. Keep the first/highest-ranked creator as the primary source,
        # while recording the other creator handles too.
        unique = {}
        for p in all_final:
            pid = str(p.get("id") or "")
            if pid not in unique:
                p["source_creators_all"] = p.get("source_creator") or ""
                unique[pid] = p
            else:
                existing = unique[pid]
                handles = [
                    x.strip() for x in str(existing.get("source_creators_all") or "").split(",")
                    if x.strip()
                ]
                new_handle = str(p.get("source_creator") or "").strip()
                if new_handle and new_handle not in handles:
                    handles.append(new_handle)
                existing["source_creators_all"] = ", ".join(handles)
        final = list(unique.values())

        file_creator = {
            "handle": (
                creators_to_scan[0].get("handle")
                if creator_source == "name"
                else f"top{len(creators_to_scan)}creators"
            ) or "creator",
            "name": scan_label,
            "creator_revenue": None,
        }
        out, imgdir, saved, pushed = write_creator_product_results(
            preset, file_creator, final
        )
        log(
            f"DONE — checked {len(creators_to_scan)} creator(s), "
            f"{total_products} creator products, {total_eligible} pre-qualified; "
            f"{len(final)} unique products passed -> {out.name}"
        )
        log(f"images -> {imgdir.name}/ ({saved}/{len(final)} downloaded)")
        if pushed:
            log(f"pushed {pushed} straight to your AI Director inbox")
        return

    # Product mode remains the existing working Sniper flow.
    if preset not in MOMENTUM_PRESETS:
        log(f"(custom preset '{preset}' — using your own saved Kalodata filter. Momentum presets: {MOMENTUM_PRESETS})")
    log(f"sniping preset: {preset}")
    pool = pull(preset)
    log(f"pulled {len(pool)} products")
    keep = []
    for p in pool:
        if any(b in p["name"].lower() for b in RESTRICTED): continue
        price = p["avg_price"] or 0
        if price < 8 or price * (p["commission"] or 0) / 100 < 3.00: continue
        keep.append(p)
    keep.sort(key=lambda x: (-(x["avg_price"] or 0 >= 50), -(x["revenue"] or 0)))
    # The AD-icon + shop safety check is MANDATORY and runs by default: it opens each
    # product's detail page and counts how many of its top videos are running ads (7+ = strong,
    # under 7 = cut). This is what keeps your TikTok account alive. Do not skip it.
    if ENV.get("SKIP_VET") == "1":
        log(f"SKIP_VET=1 set — passing ALL {len(keep)} through WITHOUT the AD safety check (review them yourself!)")
        final = keep
        for p in final:
            p.setdefault("shop", "")
            p["ads"] = None
    else:
        log(f"{len(keep)} pass filters, vetting ALL {len(keep)}")
        final = vet(keep)
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
    out = BASE / f"snipe-{preset.replace(' ','')}-{datetime.date.today()}.csv"
    saved, pushed = 0, 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # image_file/image_url lead so the AI Director import can match each row
        # to its downloaded photo. Drag the sniped-products folder into Bulk
        # Factory and drop this CSV on top; names + captions fill themselves in.
        w.writerow(["product", "image_file", "image_url", "avg_price", "revenue_7d", "growth_pct",
                    "commission_pct", "per_sale_$", "creators", "ads_top10", "shop", "tiktok_link",
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
