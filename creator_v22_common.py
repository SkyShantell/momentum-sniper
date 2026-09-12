"""Momentum Sniper V22 runtime patch fragment."""
PATCH_SOURCE = r'''
def _deep_records(obj, kind):
    """Find the most likely array of Creator or Product records inside arbitrary JSON."""
    candidates = []

    def walk(x):
        if isinstance(x, list):
            dicts = [v for v in x if isinstance(v, dict)]
            if dicts:
                score = 0
                sample = dicts[:5]
                keys = {str(k).lower() for row in sample for k in row.keys()}
                if kind == "creator":
                    if any(k in keys for k in ("creator_uid", "creator_id", "handle", "creator_handle", "nickname", "creator_nickname")):
                        score += 8
                    if any("creator" in k for k in keys):
                        score += 3
                    if "revenue" in keys:
                        score += 1
                else:
                    if any(k in keys for k in ("product_id", "product_title", "id", "title", "name")):
                        score += 5
                    if any("product" in k for k in keys):
                        score += 4
                    if any(k in keys for k in ("revenue", "sale", "unit_price", "avg_unit_price")):
                        score += 2
                candidates.append((score, len(dicts), dicts))
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)

    walk(obj)
    if not candidates:
        return []
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2] if candidates[0][0] > 0 else []

def _deep_first(obj, names):
    """Case-insensitive recursive lookup by likely key names."""
    wanted = [str(n).lower() for n in names]
    found = []

    def walk(x, depth=0):
        if depth > 7:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                kl = str(k).lower()
                if kl in wanted:
                    found.append((wanted.index(kl), v))
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x[:50]:
                walk(v, depth + 1)

    walk(obj)
    if not found:
        return None
    found.sort(key=lambda t: t[0])
    return found[0][1]

def _creator_from_json(row, rank=None):
    cid = _deep_first(row, ["creator_uid", "creator_id", "id", "uid"])
    handle = _deep_first(row, ["creator_handle", "handle", "unique_id", "uniqueId", "username"])
    name = _deep_first(row, ["creator_nickname", "nickname", "display_name", "displayName", "name"])
    revenue = _deep_first(row, ["revenue", "gmv_in_30", "gmv", "video_revenue"])
    avatar = _deep_first(row, ["avatar", "avatar_url", "avatarUrl", "profile_image", "profileImage"])

    handle = str(handle or "").strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle

    return {
        "handle": handle,
        "name": str(name or "").strip(),
        "creator_id": str(cid or "").strip(),
        "creator_page_url": (
            f"https://www.kalodata.com/creator/detail?id={cid}&language=en-US&currency=USD&region=US"
            if cid else ""
        ),
        "creator_revenue": num(revenue),
        "profile_image": str(avatar or "").strip(),
        "creator_rank": rank,
    }

def _product_from_json(row, creator):
    pid = _deep_first(row, ["product_id", "id", "productId"])
    title = _deep_first(row, ["product_title", "title", "product_name", "productName", "name"])
    revenue = _deep_first(row, ["revenue", "gmv", "video_revenue"])
    sold = _deep_first(row, ["sale", "item_sold", "itemSold", "sold"])
    unit_price = _deep_first(row, ["unit_price", "avg_unit_price", "avgUnitPrice", "price"])
    commission = _deep_first(row, ["commission_rate", "commissionRate", "commission", "commission_ratio"])
    image = _deep_first(row, ["cover", "cover_url", "coverUrl", "image", "image_url", "product_image"])

    pid = str(pid or "").strip()
    title = str(title or "").strip() or (f"Product {pid}" if pid else "Product")

    return {
        "id": pid,
        "img": str(image or "").strip() or None,
        "name": title[:180],
        "revenue": num(revenue),
        "item_sold": num(sold),
        "avg_price": num(unit_price),
        "growth": None,
        "commission": num(commission),
        "creators": None,
        "conv": None,
        "source_creator": creator.get("handle") or "",
        "source_creator_name": creator.get("name") or "",
        "source_creator_revenue": creator.get("creator_revenue"),
        "source_creator_rank": creator.get("creator_rank"),
    }

def _browser_result(vals, marker):
    """Return JSON object from the last JS result carrying marker."""
    hit = None
    for v in vals:
        if not (isinstance(v, str) and v.lstrip().startswith("{")):
            continue
        try:
            obj = json.loads(v)
        except Exception:
            continue
        if isinstance(obj, dict) and marker in obj:
            hit = obj
    return hit

CREATOR_NETWORK_CAPTURE_JS = r"""(()=>{
  const box={hits:[],installedAt:Date.now()};
  window.__momentumCreatorCapture=box;
  const matches=u=>String(u||'').includes('/creator/queryList');
  const push=(kind,url,body,status,data)=>{
    try{
      box.hits.push({kind,url:String(url||''),body:body||null,status:Number(status||0),data});
      if(box.hits.length>8)box.hits.shift();
    }catch(_){}
  };

  const nativeFetch=window.fetch.bind(window);
  window.fetch=async function(input,init){
    const url=(typeof input==='string')?input:(input?.url||'');
    const res=await nativeFetch(input,init);
    if(matches(url)){
      try{
        const clone=res.clone();
        clone.json().then(data=>push('fetch',url,init?.body||null,res.status,data)).catch(()=>{});
      }catch(_){}
    }
    return res;
  };

  const open=XMLHttpRequest.prototype.open;
  const send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(method,url,...rest){
    this.__momentumUrl=url;
    this.__momentumMethod=method;
    return open.call(this,method,url,...rest);
  };
  XMLHttpRequest.prototype.send=function(body){
    if(matches(this.__momentumUrl)){
      this.addEventListener('load',()=>{
        let data=null;
        try{data=this.responseType==='json'?this.response:JSON.parse(this.responseText||'null');}catch(_){}
        push('xhr',this.__momentumUrl,body||null,this.status,data);
      },{once:true});
    }
    return send.call(this,body);
  };
  return 'creator-json-capture-installed';
})()"""

CREATOR_NETWORK_CAPTURE_READ_JS = r"""JSON.stringify({
  creator_capture: window.__momentumCreatorCapture || null
})"""

def _start_internal_fetch_js(result_key, path, body):
    """Fire one authenticated same-origin Kalodata POST and store its JSON on window."""
    return f"""(()=>{{
      window[{json.dumps(result_key)}]={{pending:true}};
      fetch({json.dumps(path)}, {{
        method:'POST',
        credentials:'include',
        headers:{{
          'accept':'application/json, text/plain, */*',
          'content-type':'application/json',
          'country':'US',
          'currency':'USD',
          'language':'en-US'
        }},
        body:JSON.stringify({json.dumps(body)})
      }}).then(async r=>{{
        let j=null,t='';
        try{{j=await r.clone().json();}}catch(_){{
          try{{t=await r.text();}}catch(__){{}}
        }}
        window[{json.dumps(result_key)}]={{pending:false,status:r.status,json:j,text:t.slice(0,1000)}};
      }}).catch(e=>{{
        window[{json.dumps(result_key)}]={{pending:false,status:0,error:String(e)}};
      }});
      return 'internal-fetch-started';
    }})()"""

def _read_internal_fetch_js(result_key, marker):
    return f"""JSON.stringify({{{json.dumps(marker)}:window[{json.dumps(result_key)}]||null}})"""
'''

def install(legacy):
    exec(PATCH_SOURCE, legacy.__dict__)
