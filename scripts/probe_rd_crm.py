"""Sondagem temporária: com que campanha/origem/funil chegam os negócios recentes. Só contagens."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from collections import Counter
import fetch_rd_crm as f
tok = os.environ["RD_CRM_TOKEN"].strip()
deals, page = [], 1
while True:
    d = f.get(tok, "/deals", {"page": page, "limit": 200}); deals += d.get("deals", [])
    if not d.get("has_more") or page >= 200: break
    page += 1
rec = [x for x in deals if (x.get("created_at") or "")[:10] >= "2026-11-10"]
nm = f.name_of
print("negócios desde 10/11:", len(rec))
print("por dia x campanha:")
for k, n in sorted(Counter(((x.get("created_at") or "")[:10], nm(x.get("campaign"))) for x in rec).items()):
    print(" ", k, n)
print("origem:", Counter(nm(x.get("deal_source")) for x in rec))
print("funil:", Counter(nm(x.get("deal_pipeline")) for x in rec))
print("etapa:", Counter(nm(x.get("deal_stage")) for x in rec))
print("campanhas cadastradas:", [c.get("name") for c in f.get(tok, "/campaigns").get("campaigns", [])])
