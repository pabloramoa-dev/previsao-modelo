"""Triagem nacional centralizada; nunca publica. Evidências RSS não são fatos confirmados."""
import csv, json, os, re, argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from monitor_defesa_civil_brasil import parse, FEED, UFS, norm, SULFLU

ACTIVE={"RJ":"previsao-rj","SP":"o-tempo-sp","PR":"previsao-pr","RS":"previsao-rs","MG":"previsaomg","DF":"previsao-bsb","BA":"previsaobahia"}
WORDS=("enchente","inundacao","alagamento","transbord","deslizamento","enxurrada","granizo","vendaval","temporal","interdicao","sirenes")
def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"PrevisaoRadar/1.0"}),timeout=25) as r:
        b=r.read(30000001)
    if len(b)>30000000: raise ValueError("resposta excessiva")
    return b
def xml(b):
    if b"<!DOCTYPE" in b.upper() or b"<!ENTITY" in b.upper(): raise ValueError("XML inseguro")
    return ET.fromstring(b)
def route(code):
    return "previsao-sul-fluminense" if code in SULFLU else ACTIVE.get(UFS.get(code[:2]))
def triggers(vals):
    if len(vals)<72 or any(v is None for v in vals[-72:]): return []
    return [f"{n}h >= {limit} mm" for n,limit in [(1,20),(3,40),(24,50),(48,80),(72,120)] if sum(vals[-n:])>=limit]
def news(city,uf,now):
    query=f'"{city}" {uf} (enchente OR alagamento OR transbordamento OR deslizamento OR temporal OR granizo OR vendaval) when:1d'
    url="https://news.google.com/rss/search?"+urlencode({"q":query,"hl":"pt-BR","gl":"BR","ceid":"BR:pt-419"})
    out=[]
    for item in xml(fetch(url)).findall(".//item"):
        title=item.findtext("title") or ""
        try: date=parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError,ValueError): continue
        if not now-timedelta(hours=24)<=date<=now+timedelta(minutes=5): continue
        if norm(city) not in norm(title) or not any(w in norm(title) for w in WORDS): continue
        out.append({"titulo":title,"url":item.findtext("link"),"veiculo":item.findtext("source"),"publicado":date.isoformat(),"status":"pista_nao_validada"})
    return out[:12]
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test:
        assert triggers([0]*71+[20])==["1h >= 20 mm"]
        assert "24h >= 50 mm" in triggers([0]*48+[3]*24)
        assert not triggers([None]*72)
        assert route("3300407")=="previsao-sul-fluminense"
        print("Testes básicos OK"); return
    now=datetime.now(timezone.utc)
    cities=list(csv.DictReader(Path(__file__).with_name("municipios.csv").open(encoding="utf-8-sig")))
    cities=[c for c in cities if route(c["codigo_ibge"])]
    alerts={}; errors=[]; candidates=[]
    try:
        for a in parse(fetch(FEED),now)["avisos"]:
            for c in a["ibge"]: alerts.setdefault(c,[]).append(a)
    except Exception as e: errors.append({"fonte":"IDAP","erro":str(e)})
    # Sem API meteorológica comercial contratada: triagem CAP cobre todos os códigos
    # cadastrados; acumulados por município exigem fonte em lote autorizada.
    for c in cities:
        code=c["codigo_ibge"]
        if code in alerts:
            candidates.append({"ibge":code,"cidade":c["nome"],"uf":UFS[code[:2]],"canal":route(code),"alertas":alerts[code],"status":"investigar"})
    candidates.sort(key=lambda c: not any(a["severidade"] in ("Severe","Extreme") for a in c["alertas"]))
    limit=20
    for c in candidates[:limit]:
        try: c["noticias"]=news(c["cidade"],c["uf"],now)
        except Exception as e: c["erro_rss"]=str(e)
    result={"consultado_em":now.isoformat(),"modo":"simulacao_sem_publicacao","municipios_catalogados":len(cities),"triagem":"CAP geocodificado; chuva quantitativa ainda não conectada","candidatos":candidates,"limite_investigacoes_rss":limit,"erros":errors}
    out=Path("output/radar_regional.json");out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Municípios cadastrados: {len(cities)}; candidatos CAP: {len(candidates)}; falhas de fonte: {len(errors)}")
    if errors: raise SystemExit(1)
if __name__=="__main__": main()
