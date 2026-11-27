"""Relatório nacional de avisos meteorológicos/hidrológicos da Defesa Civil.
Não publica nem aciona canais: a elegibilidade local precisa ser validada.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

FEED = "https://idapfile.mdr.gov.br/idap/api/rss/cap"
NS = "{urn:oasis:names:tc:emergency:cap:1.2}"
TZ = ZoneInfo("America/Sao_Paulo")
UFS = dict(zip("11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53".split(),
               "RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF".split()))
CANAIS = {"MG":"previsaomg", "SP":"o-tempo-sp",
          "PR":"previsao-pr", "RS":"previsao-rs", "DF":"previsao-bsb", "BA":"previsaobahia"}
SULFLU = {"3306305","3300407","3304110","3304201","3300308","3304003",
          "3302254","3304128","3303955","3304409"}
RJ_METRO = {"3304557","3303302","3301702","3303500","3304904","3300456",
            "3305109","3303203","3301900","3302700"}
METEO = ("tempestade","temporal","chuva","precipitacao","granizo","inunda",
         "alaga","enchente","enxurrada","deslizamento","movimento de massa",
         "vendaval","vento forte","rajada","tornado","ciclone","tufao","furacao",
         "ressaca","queda de barreira")
def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().casefold()
def get(node,k):
    return (node.findtext(NS+k) or "").strip()
def time(s):
    t = datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("timestamp sem fuso")
    return t
def parse(raw, now):
    if len(raw)>30_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML fora dos limites")
    root=ET.fromstring(raw)
    nodes=list(root.iter(NS+"alert"))
    if not nodes and root.tag not in ("{http://www.w3.org/2005/Atom}feed","rss"):
        raise ValueError("feed não reconhecido")
    # Updates e cancels substituem as mensagens referenciadas, inclusive em
    # alertas vencidos. Usar remetente, identificador e data CAP como chave.
    superseded=set()
    for a in nodes:
        if get(a,"status")!="Actual" or get(a,"scope")!="Public" or get(a,"msgType") not in ("Update","Cancel"):
            continue
        try:
            if time(get(a,"sent"))>now+timedelta(minutes=5): continue
        except ValueError: continue
        for ref in get(a,"references").split():
            parts=ref.split(",")
            if len(parts)==3 and parts[0]==get(a,"sender"):
                superseded.add(tuple(parts))
    records={}
    unmatched=[]
    for a in nodes:
        key=tuple(get(a,k) for k in ("sender","identifier","sent"))
        if not all(key) or key in superseded: continue
        if get(a,"status")!="Actual" or get(a,"scope")!="Public" or get(a,"msgType") not in ("Alert","Update"):
            continue
        try:
            sent=time(key[2])
            if sent>now+timedelta(minutes=5): continue
        except ValueError: continue
        for i,info in enumerate(a.findall(NS+"info")):
            if "defesa civil" not in norm(get(info,"senderName")+" "+key[0]).replace("_"," ").replace("-"," "):
                continue
            event=get(info,"event")
            if not any(w in norm(event) for w in METEO): continue
            try:
                start=time(get(info,"onset") or get(info,"effective") or key[2])
                end=time(get(info,"expires"))
            except ValueError: continue
            if end<=max(now,start) or start>now+timedelta(hours=24): continue
            severity=get(info,"severity")
            if severity not in ("Minor","Moderate","Severe","Extreme"): continue
            codes=set()
            areas=[]
            for area in info.findall(NS+"area"):
                areas.append(get(area,"areaDesc"))
                for geo in area.findall(NS+"geocode"):
                    name=norm(get(geo,"valueName"))
                    if "ibge" not in name and "brasil" not in name: continue
                    for code in re.split(r"[,;\s]+",get(geo,"value")):
                        if re.fullmatch(r"\d{7}",code) and code[:2] in UFS: codes.add(code)
            rec={"id":key[1],"emitido":sent.isoformat(),"orgao":get(info,"senderName") or key[0],
                 "evento":event,"severidade":severity,"inicio":start.isoformat(),"fim":end.isoformat(),
                 "areas":areas,"ibge":sorted(codes),"ufs":sorted({UFS[c[:2]] for c in codes}),
                 "descricao":get(info,"description"),"instrucoes":get(info,"instruction"),
                 "fonte":FEED,"canais_candidatos":[]}
            candidates={CANAIS[uf] for uf in rec["ufs"] if uf in CANAIS}
            if codes & RJ_METRO: candidates.add("previsao-rj")
            if codes & SULFLU: candidates.add("previsao-sul-fluminense")
            rec["canais_candidatos"]=sorted(candidates)
            if codes: records[(key,i)]=rec
            else: unmatched.append(rec)
    return {"avisos":list(records.values()),"sem_geocodigo_para_revisao":unmatched}
def self_test():
    now=datetime.fromisoformat("2026-11-25T08:00:00-03:00")
    def alert(id,typ="Alert",refs="",status="Actual",expires="2026-11-25T23:59:00-03:00"):
        return f"""<alert xmlns="{NS[1:-1]}"><identifier>{id}</identifier><sender>defesa-civil@example.test</sender>
        <sent>2026-11-25T07:00:00-03:00</sent><status>{status}</status><scope>Public</scope><msgType>{typ}</msgType>
        <references>{refs}</references><info><senderName>Defesa Civil</senderName><event>Tempestade / Vendaval</event>
        <severity>Severe</severity><onset>2026-11-25T07:00:00-03:00</onset><expires>{expires}</expires>
        <area><areaDesc>Volta Redonda e Curitiba</areaDesc><geocode><valueName>IBGE</valueName><value>3306305,4106902</value></geocode></area>
        </info></alert>"""
    # XML CAP pode vir dentro de feed Atom.
    def run(*alerts): return parse(('<feed xmlns="http://www.w3.org/2005/Atom">'+''.join(alerts)+'</feed>').encode(),now)
    a=run(alert("a"))["avisos"][0]
    assert a["ufs"]==["PR","RJ"] and "previsao-sul-fluminense" in a["canais_candidatos"]
    assert not run(alert("a",status="Test"))["avisos"]
    assert not run(alert("a",expires="2026-11-25T07:30:00-03:00"))["avisos"]
    assert not run(alert("a"),alert("c","Cancel","defesa-civil@example.test,a,2026-11-25T07:00:00-03:00"))["avisos"]
    print("Testes sintéticos IDAP concluídos.")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test: self_test(); return
    now=datetime.now(TZ)
    out=Path("output/alertas_defesa_civil_brasil.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    try:
        with urlopen(Request(FEED,headers={"User-Agent":"PrevisaoBrasil/1.0"}),timeout=45) as r:
            if r.geturl().split("/")[2]!=FEED.split("/")[2]:
                raise ValueError("redirecionamento inesperado")
            data=parse(r.read(30_000_001),now)
    except Exception as exc:
        out.write_text(json.dumps({"status":"indisponivel","consultado_em":now.isoformat(),
                                    "fonte":FEED,"erro":str(exc)},ensure_ascii=False),encoding="utf-8")
        print("Fonte indisponível; não significa ausência de alertas.",file=sys.stderr)
        raise
    data.update(status="ok",consultado_em=now.isoformat(),fonte=FEED)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print("## Defesa Civil nacional - "+now.strftime("%d/%m/%Y %H:%M"))
    print(f"Fonte: {FEED}. Canais são candidatos; conferir cobertura local antes de publicar.")
    for uf in sorted(UFS.values()):
        n=sum(uf in a["ufs"] for a in data["avisos"])
        print(f"- {uf}: {n} alertas com geocódigo confirmado")
    print(f"Sem geocódigo para revisão manual: {len(data['sem_geocodigo_para_revisao'])}")
if __name__=="__main__":
    main()
