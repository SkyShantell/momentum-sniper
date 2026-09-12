"""Momentum Sniper V22 runtime patch fragment."""
PATCH_SOURCE = r'''
def vet_creator_products(cands):
    """Strict Creator-product vet using Kalodata internal JSON, not rendered DOM."""
    if not cands:
        return []

    kept = []
    end = datetime.date.today() - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=6)
    wide_end = end + datetime.timedelta(days=1)
    wide_start = wide_end - datetime.timedelta(days=89)

    # Small chunks keep Kalodata's internal endpoint load reasonable while avoiding
    # the old scroll/click/new-tab loop.
    for offset in range(0, len(cands), 4):
        chunk = cands[offset:offset + 4]
        payload = [
            {
                "id": str(p["id"]),
                "candidatePrice": p.get("avg_price"),
                "candidateCommission": p.get("commission"),
                "candidateImage": p.get("img"),
            }
            for p in chunk
        ]

        key = f"__momentumVet_{offset}"
        marker = "product_vet"
        start_js = f"""(()=>{{
          window[{json.dumps(key)}]={{pending:true}};
          const products={json.dumps(payload)};
          const headers={{
            'accept':'application/json, text/plain, */*',
            'content-type':'application/json',
            'country':'US',
            'currency':'USD',
            'language':'en-US'
          }};

          const post=async(path,body)=>{{
            try{{
              const r=await fetch(path,{{
                method:'POST',credentials:'include',headers,body:JSON.stringify(body)
              }});
              let j=null,t='';
              try{{j=await r.clone().json();}}catch(_){{
                try{{t=await r.text();}}catch(__){{}}
              }}
              return {{status:r.status,json:j,text:t.slice(0,500)}};
            }}catch(e){{return {{status:0,error:String(e)}};}}
          }};

          const dataObj=x=>{{
            if(!x)return {{}};
            if(x.data && !Array.isArray(x.data))return x.data;
            return x;
          }};
          const rows=x=>{{
            if(!x)return [];
            if(Array.isArray(x.data))return x.data;
            if(Array.isArray(x.list))return x.list;
            if(Array.isArray(x.items))return x.items;
            if(x.data && Array.isArray(x.data.list))return x.data.list;
            if(x.data && Array.isArray(x.data.items))return x.data.items;
            return [];
          }};
          const n=v=>{{
            if(v===null||v===undefined||v==='')return null;
            if(typeof v==='number')return Number.isFinite(v)?v:null;
            const s=String(v).replace(/,/g,'').replace(/\\$/g,'').replace(/%/g,'').trim();
            const m=s.match(/^(-?[\\d.]+)\\s*([kKmMbB])?$/);
            if(!m)return null;
            let x=Number(m[1]);
            if(!Number.isFinite(x))return null;
            if(m[2]){{
              const z=m[2].toLowerCase();
              if(z==='k')x*=1e3; else if(z==='m')x*=1e6; else if(z==='b')x*=1e9;
            }}
            return x;
          }};
          const findKV=(obj,re,depth=0)=>{{
            if(depth>7||obj===null||obj===undefined)return null;
            if(Array.isArray(obj)){{
              for(const v of obj.slice(0,60)){{
                const z=findKV(v,re,depth+1); if(z)return z;
              }}
              return null;
            }}
            if(typeof obj==='object'){{
              for(const [k,v] of Object.entries(obj)){{
                if(re.test(String(k)))return {{key:k,value:v}};
              }}
              for(const v of Object.values(obj)){{
                const z=findKV(v,re,depth+1); if(z)return z;
              }}
            }}
            return null;
          }};
          const collectUrls=(obj,id,out=[],depth=0)=>{{
            if(depth>7||out.length>=12||obj===null||obj===undefined)return out;
            if(typeof obj==='string'){{
              if(/^https?:\\/\\//i.test(obj) && (
                obj.includes('tiktok.product/'+id+'/') ||
                /tiktokcdn|p16-oec|kalocdn|byteimg|\\.jpe?g|\\.png|\\.webp/i.test(obj)
              ) && !out.includes(obj)) out.push(obj);
              return out;
            }}
            if(Array.isArray(obj)){{
              for(const v of obj.slice(0,80))collectUrls(v,id,out,depth+1);
            }} else if(typeof obj==='object'){{
              for(const v of Object.values(obj))collectUrls(v,id,out,depth+1);
            }}
            return out;
          }};
          const isAd=v=>{{
            const x=v?.is_ad ?? v?.isAd ?? v?.ad ?? v?.is_ads ?? v?.ad_flag ?? v?.adFlag;
            if(x===true||x===1||x==='1')return true;
            if(typeof x==='string' && /^(true|yes|ad)$/i.test(x.trim()))return true;
            return false;
          }};

          (async()=>{{
            const out=[];
            for(const p of products){{
              const base={{id:p.id,startDate:{json.dumps(str(start))},endDate:{json.dumps(str(end))},authority:true}};
              const paged={{...base,pageNo:1,pageSize:10,sort:[{{field:'revenue',type:'DESC'}}]}};
              const wide={{id:p.id,startDate:{json.dumps(str(wide_start))},endDate:{json.dumps(str(wide_end))},authority:true}};

              const [detailRes,totalRes,videoRes]=await Promise.all([
                post('/product/detail',wide),
                post('/product/detail/total',base),
                post('/product/detail/video/queryList',paged),
              ]);

              const detail=dataObj(detailRes.json);
              const total=dataObj(totalRes.json);
              const videos=rows(videoRes.json).slice(0,10);

              const commKV=findKV(detail,/commission/i) || findKV(detailRes.json,/commission/i);
              let commission=n(commKV?.value);
              if(commission!==null && commission>0 && commission<=1 &&
                 /rate|ratio|percent|pct/i.test(commKV?.key||'')) commission*=100;
              if(commission===null)commission=n(p.candidateCommission);

              let price=n(
                total.unit_price ?? total.avg_unit_price ?? total.avgUnitPrice ??
                detail.unit_price ?? detail.avg_unit_price ?? p.candidatePrice
              );

              const titleKV=findKV(detail,/^(product_title|product_name|title)$/i);
              const shopKV=findKV(detail,/^(shop_name|seller_name|store_name)$/i);
              const brandKV=findKV(detail,/^brand_name$/i);
              const urls=collectUrls(detail,p.id,[]);
              if(p.candidateImage && !urls.includes(p.candidateImage))urls.unshift(p.candidateImage);

              out.push({{
                id:p.id,
                status:{{
                  detail:detailRes.status,total:totalRes.status,videos:videoRes.status
                }},
                commission,
                commissionKey:commKV?.key||null,
                price,
                ads:videos.filter(isAd).length,
                videoRows:videos.length,
                title:titleKV?.value||null,
                shop:shopKV?.value||brandKV?.value||detail.name||'',
                img:urls[0]||null,
                imgs:urls.slice(0,8),
                endpointError:
                  detailRes.error||totalRes.error||videoRes.error||
                  detailRes.text||totalRes.text||videoRes.text||null
              }});
            }}
            window[{json.dumps(key)}]={{pending:false,items:out}};
          }})().catch(e=>{{
            window[{json.dumps(key)}]={{pending:false,error:String(e),items:[]}};
          }});

          return 'internal-product-vet-started';
        }})()"""

        read_js = f"""JSON.stringify({{{json.dumps(marker)}:window[{json.dumps(key)}]||null}})"""
        acts = login_actions() + [
            {"type": "executeJavascript", "script": "location.assign('https://www.kalodata.com/product')"},
            {"type": "wait", "milliseconds": 3500},
            {"type": "executeJavascript", "script": start_js},
            {"type": "wait", "milliseconds": 9500},
            {"type": "executeJavascript", "script": read_js},
        ]
        vals = fc(acts, f"creator-product-json-vet:{offset//4 + 1}")
        wrap = _browser_result(vals, marker) or {}
        result = wrap.get(marker) or {}
        details = result.get("items") or []

        if result.get("pending"):
            raise RuntimeError("Kalodata internal product vet was still pending after the wait window.")
        if result.get("error"):
            raise RuntimeError(f"Kalodata internal product vet failed: {result['error']}")
        if not details:
            raise RuntimeError("Kalodata internal product vet returned no product detail records.")

        by_id = {str(d.get("id")): d for d in details if isinstance(d, dict)}
        for p in chunk:
            d = by_id.get(str(p["id"]))
            if not d:
                log(f"  cut  {p['name'][:48]} | no internal detail result")
                continue

            statuses = d.get("status") or {}
            if any(int(statuses.get(k) or 0) != 200 for k in ("detail", "total", "videos")):
                log(
                    f"  cut  {p['name'][:48]} | internal HTTP "
                    f"{statuses.get('detail')}/{statuses.get('total')}/{statuses.get('videos')}"
                )
                continue

            price = d.get("price")
            commission = d.get("commission")
            ads = d.get("ads")
            video_rows = int(d.get("videoRows") or 0)

            p["avg_price"] = float(price) if isinstance(price, (int, float)) else (p.get("avg_price") or 0)
            p["commission"] = float(commission) if isinstance(commission, (int, float)) else None
            p["ads"] = int(ads) if isinstance(ads, (int, float)) else None
            p["shop"] = str(d.get("shop") or "").strip()
            p["per_sale"] = (
                round(p["avg_price"] * p["commission"] / 100, 2)
                if p["commission"] is not None else None
            )

            if d.get("title") and (not p.get("name") or p["name"].startswith("Product ")):
                p["name"] = str(d["title"])[:180]
            if d.get("img"):
                p["img"] = d["img"]
            if d.get("imgs"):
                p["detail_imgs"] = list(d["imgs"])[:8]

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

            if p["avg_price"] < 8:
                log(f"  cut  {p['name'][:48]} | avg ${p['avg_price']:.2f} < $8")
                continue
            if p["commission"] is None:
                log(
                    f"  cut  {p['name'][:48]} | commission unreadable from internal JSON"
                    f"{' (' + str(d.get('commissionKey')) + ')' if d.get('commissionKey') else ''}"
                )
                continue
            if p["per_sale"] < 3.00:
                log(f"  cut  {p['name'][:48]} | ${p['per_sale']:.2f}/sale < $3")
                continue
            if p["ads"] is None or video_rows == 0:
                log(f"  cut  {p['name'][:48]} | video/ad JSON unreadable")
                continue
            if p["ads"] < 7:
                log(f"  cut  {p['name'][:48]} | ads {p['ads']}/{video_rows or 10}")
                continue
            if not brand_ok:
                log(f"  cut  {p['name'][:48]} | shop={shop!r} brand safety")
                continue

            kept.append(p)
            log(
                f"  KEEP {p['name'][:48]} | {p.get('source_creator') or 'creator'} "
                f"| ${p['avg_price']:.2f} | ${p['per_sale']:.2f}/sale "
                f"| ads {p['ads']}/{video_rows or 10} | JSON"
            )

        time.sleep(4)

    return kept
'''

def install(legacy):
    exec(PATCH_SOURCE, legacy.__dict__)
