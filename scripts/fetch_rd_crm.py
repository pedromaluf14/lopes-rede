"""Busca o funil comercial da Rede Lopes no RD Station CRM e grava em crm.json.

Roda no GitHub Actions junto com o fetch do Windsor (ver atualizar-dados.yml).
O token vem do secret RD_CRM_TOKEN — nunca coloque o token no código.

Este repositório é PÚBLICO: o crm.json guarda SÓ contagens por dia. Nenhum nome,
telefone, e-mail ou outro dado de lead sai daqui.

Quais negócios entram: os da campanha do RD "LUZIAC - Leads" (leads dos anúncios),
no funil "Funil Vendas".

Contagem "chegou até": um negócio que hoje está em COF Enviada conta também em
VP Agendada e VP Realizada. Negócio ganho conta em todas as etapas e em Venda.
A data de cada negócio é a data em que ele entrou no RD (created_at).

Formato de saída (lido pelo index.html):
{
  "updatedAt": "...",
  "stages": ["Leads na RD", "VP Agendada", ...],      # rótulos, na ordem do funil
  "daily": {"AAAA-MM-DD": [n0, n1, ...], ...},         # n_i = negócios criados no dia que chegaram até a etapa i
  "status": {"AAAA-MM-DD": [abertos, perdidos, ganhos], ...}
}
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

API = "https://crm.rdstation.com/api/v1"
CAMPAIGN = "LUZIAC - Leads"      # campanha do RD onde caem os leads dos anúncios
PIPELINE = "Funil Vendas"
# Etapas do RD, na ordem do funil, e o rótulo mostrado no painel.
# A 1ª (Qualificação) vira "Leads na RD": todo negócio passa por ela.
STAGES = [
    ("Qualificação", "Leads na RD"),
    ("VP Agendada", "VP Agendada"),
    ("VP Realizada", "VP Realizada"),
    ("COF Enviada", "COF Enviada"),
    ("COF Assinada", "COF Assinada"),
    ("Contrato venda enviado", "Contrato enviado"),
]
OUT = os.path.join(os.path.dirname(__file__), "..", "crm.json")


class CrmError(Exception):
    pass


def norm(s):
    return " ".join(str(s or "").split()).casefold()


def get(token, path, params=None):
    q = dict(params or {})
    q["token"] = token
    url = f"{API}{path}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "luziac-painel"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < 2:   # limite de requisições: espera e tenta de novo
                time.sleep(15)
                continue
            raise CrmError(f"HTTP {e.code} em {path}: {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:
            if tentativa < 2:
                time.sleep(5)
                continue
            raise CrmError(f"{type(e).__name__} em {path}: {e}"[:400])


def name_of(x):
    return x.get("name") if isinstance(x, dict) else x


def main() -> int:
    token = (os.environ.get("RD_CRM_TOKEN") or "").strip()
    if not token:
        print("::error::RD_CRM_TOKEN não definido")
        return 1
    try:
        pipes = get(token, "/deal_pipelines")
        pipe = next((p for p in pipes if norm(p.get("name")) == norm(PIPELINE)), None)
        if not pipe:
            raise CrmError(f'funil "{PIPELINE}" não encontrado: {[p.get("name") for p in pipes]}')
        stage_idx = {}
        for i, (rd_name, _) in enumerate(STAGES):
            st = next((s for s in pipe.get("deal_stages", []) if norm(s.get("name")) == norm(rd_name)), None)
            if not st:
                raise CrmError(f'etapa "{rd_name}" não existe mais no funil — atualize STAGES em fetch_rd_crm.py')
            stage_idx[st["id"]] = i

        deals, page = [], 1
        while True:
            data = get(token, "/deals", {"page": page, "limit": 200})
            deals += data.get("deals", [])
            if not data.get("has_more") or page >= 200:
                break
            page += 1
    except CrmError as e:
        print(f"::error::ERRO RD CRM {e}")
        return 1

    n_st = len(STAGES)
    daily = defaultdict(lambda: [0] * (n_st + 1))   # +1 = Venda
    status = defaultdict(lambda: [0, 0, 0])
    skipped = 0
    for d in deals:
        if norm(name_of(d.get("campaign"))) != norm(CAMPAIGN):
            continue
        st = d.get("deal_stage") or {}
        idx = stage_idx.get(st.get("id") if isinstance(st, dict) else st)
        day = (d.get("created_at") or "")[:10]   # o RD já devolve no fuso de Brasília
        if idx is None or len(day) != 10:
            skipped += 1   # negócio de outro funil ou sem data
            continue
        won = d.get("win") is True
        top = n_st - 1 if won else idx
        row = daily[day]
        for i in range(top + 1):
            row[i] += 1
        if won:
            row[n_st] += 1
        if won:
            status[day][2] += 1
        elif d.get("win") is False:
            status[day][1] += 1
        else:
            status[day][0] += 1

    total = sum(r[0] for r in daily.values())
    if total == 0:
        # Não sobrescreve dados bons com um retorno vazio (falha temporária da API)
        print("RD CRM retornou 0 negócios da campanha; mantendo crm.json anterior")
        return 0

    out = {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "campaign": CAMPAIGN,
        "stages": [label for _, label in STAGES] + ["Venda"],
        "daily": dict(sorted(daily.items())),
        "status": dict(sorted(status.items())),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(deals)} negócios lidos; {total} da campanha {CAMPAIGN} gravados em crm.json"
          + (f" ({skipped} ignorados: outro funil ou sem data)" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
