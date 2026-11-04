"""Sondagem do RD Station CRM (Rede Lopes).

Imprime SÓ dados agregados (funis, etapas, contagens, nomes de campos e de
campanhas/origens). Nunca imprime nome, telefone ou e-mail de lead, porque o
log do Action deste repositório é público.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter

TOKEN = os.environ.get("RD_CRM_TOKEN", "").strip()
if not TOKEN:
    print("ERRO: secret RD_CRM_TOKEN vazio")
    sys.exit(1)

V1 = "https://crm.rdstation.com/api/v1"


def get(path, params=None):
    params = dict(params or {})
    params["token"] = TOKEN
    url = f"{V1}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "luziac-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode(errors="replace")[:300])


def section(t):
    print(f"\n===== {t} =====")


status, user = get("/token/check")
section("token/check")
print("status:", status)

status, pipes = get("/deal_pipelines")
section("FUNIS")
print("status:", status)
if status != 200:
    print(pipes)
    sys.exit(1)
for p in pipes:
    print(f"- {p.get('name')} (id {p.get('id')})")
    for s in p.get("deal_stages", []):
        print(f"    {s.get('order', '')}. {s.get('name')} (id {s.get('id')})")

# Negócios: pagina tudo (limite de segurança)
deals = []
page = 1
while page <= 60:
    status, data = get("/deals", {"page": page, "limit": 200})
    if status != 200:
        print("deals status", status, data)
        break
    batch = data.get("deals", []) if isinstance(data, dict) else []
    deals += batch
    if not data.get("has_more"):
        break
    page += 1
section("NEGÓCIOS")
print("total lidos:", len(deals), "| total informado:", data.get("total") if isinstance(data, dict) else "?")

if deals:
    section("CHAVES DE UM NEGÓCIO (sem valores)")
    print(sorted(deals[0].keys()))

    def nm(x):
        return (x or {}).get("name") if isinstance(x, dict) else x

    section("POR FUNIL / ETAPA")
    c = Counter((nm(d.get("deal_pipeline")) if d.get("deal_pipeline") else "?", nm(d.get("deal_stage"))) for d in deals)
    for (p, s), n in sorted(c.items(), key=lambda x: (str(x[0][0]), -x[1])):
        print(f"{p} | {s}: {n}")

    section("STATUS (win)")
    print(Counter(str(d.get("win")) for d in deals))

    section("ORIGEM (deal_source)")
    for k, n in Counter(nm(d.get("deal_source")) for d in deals).most_common(30):
        print(f"{k}: {n}")

    section("CAMPANHA (campaign)")
    for k, n in Counter(nm(d.get("campaign")) for d in deals).most_common(30):
        print(f"{k}: {n}")

    section("CAMPOS PERSONALIZADOS (rótulo: valores mais comuns)")
    cf = {}
    for d in deals:
        for f in d.get("deal_custom_fields") or []:
            lab = (f.get("custom_field") or {}).get("label") or f.get("custom_field_id")
            cf.setdefault(lab, Counter())[str(f.get("value"))[:60]] += 1
    for lab, cnt in cf.items():
        # só mostra valores de campos com cara de origem/UTM; dos outros, só quantos distintos
        if any(k in str(lab).lower() for k in ("utm", "camp", "origem", "fonte", "conjunto", "anúncio", "anuncio", "public", "ad")):
            print(f"{lab}: {cnt.most_common(15)}")
        else:
            print(f"{lab}: {len(cnt)} valores distintos")

    section("CRIAÇÃO (mês)")
    print(sorted(Counter((d.get("created_at") or "")[:7] for d in deals).items()))

status, srcs = get("/deal_sources")
section("ORIGENS CADASTRADAS")
print(status, [s.get("name") for s in (srcs.get("deal_sources", []) if isinstance(srcs, dict) else [])])
status, camps = get("/campaigns")
section("CAMPANHAS CADASTRADAS")
print(status, [s.get("name") for s in (camps.get("campaigns", []) if isinstance(camps, dict) else [])][:50])
