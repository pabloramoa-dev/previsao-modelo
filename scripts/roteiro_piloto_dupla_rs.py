"""Roteiro em dupla: previsao *real* do MET Norway gerada na hora da renderizacao."""
import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml

FUSO = ZoneInfo("America/Sao_Paulo")
REGIOES = [
    ("Grande Porto Alegre", "porto_alegre"),
    ("Serra Gaúcha", "caxias_do_sul"),
    ("Litoral Norte", "tramandai"),
    ("Sul e Campanha", "pelotas"),
    ("Centro", "santa_maria"),
    ("Norte", "passo_fundo"),
]

def montar(snapshot, saida):
    agora = dt.datetime.now(FUSO)
    gerado = dt.datetime.fromisoformat(snapshot["generated_at"].replace("Z","+00:00"))
    if gerado.tzinfo is None:
        raise ValueError("Snapshot sem fuso e procedencia")
    if (agora - gerado.astimezone(FUSO)).total_seconds() > 10800:
        raise ValueError("Previsao com mais de 3 horas: nao renderizar")
    met = [s for s in snapshot.get("sources",[]) if "met_no" in s.get("name","").lower() or "met norway" in s.get("name","").lower()]
    if not met or not any(s.get("status") in ("ok","success","partial") for s in met):
        raise ValueError("MET Norway indisponivel: nao substituir por numeros ficticios")
    dia = snapshot["forecast"].get("tomorrow") or {}
    data = dt.date.fromisoformat(dia["date"])
    if data != agora.date() + dt.timedelta(days=1):
        raise ValueError(f"Data incorreta: esperado amanha, recebido {data}")
    por_id = {l["id"]:l for l in dia["locations"]}
    cidades=[]
    for regiao, ident in REGIOES:
        l = por_id.get(ident)
        if not l or l.get("min_c") is None or l.get("max_c") is None or l.get("rain_mm") is None:
            raise ValueError(f"Dados insuficientes em {regiao}: abortar o video")
        cidades.append(dict(regiao=regiao,nome=l["name"],
                           mi=round(float(l["min_c"])),ma=round(float(l["max_c"])),
                           mm=round(float(l["rain_mm"]),1)))
    nome_dia=["segunda-feira","terça-feira","quarta-feira","quinta-feira","sexta-feira","sábado","domingo"][data.weekday()]
    data_fala=f"{nome_dia}, dia {data.day} de novembro"
    falas=[
      {"cena":"abertura","quem":"bia",
       "fala":f"Olá, gaúchos! Eu sou a Bia. Confira a previsão para {data_fala}, com dados atualizados do serviço meteorológico MET Norway."},
      {"cena":"frase","quem":"bira",
       "fala":"E eu sou o Bira! Vamos percorrer seis regiões do Rio Grande do Sul. Na tela, temperaturas e chuva prevista em milímetros."}
    ]
    for i,c in enumerate(cidades):
        mm=c["mm"]
        q="Sem chuva significativa prevista." if mm<0.5 else f"Volume previsto de {mm:g} milímetros de chuva."
        falas.append({"cena":"numero","quem":"bia" if i%2==0 else "bira",
          "icone":"chuva" if mm >= 0.5 else "sol",
          "numero":f'{c["ma"]}°C',"sub":c["nome"].upper(),
          "local":f'MÍN {c["mi"]}°C  ·  CHUVA {mm:g} mm',
          "fala":f'Em {c["nome"]}, mínima de {c["mi"]} e máxima de {c["ma"]} graus. {q}'})
    destaque=max(cidades,key=lambda c:c["mm"])
    if destaque["mm"]>=1:
        falas.append({"cena":"frase","quem":"bia",
          "fala":f'O maior volume de chuva entre esses seis pontos foi previsto para {destaque["nome"]}, com cerca de {destaque["mm"]:g} milímetros. Não é um alerta oficial de temporal.'})
    else:
        falas.append({"cena":"frase","quem":"bia",
          "fala":"Esses são acumulados previstos, e não chuva já observada. A situação pode mudar nas próximas atualizações."})
    falas.append({"cena":"cta","quem":"bira","chamada":"COMPARTILHE A PREVISÃO",
      "sub":"@previsaors · Rio Grande do Sul",
      "fala":"Salve a previsão e mande para quem mora no Rio Grande do Sul. Siga o Previsão RS!"})
    titulo="PREVISÃO DO RS"
    report=f"Previsão para {data.isoformat()} • atualização {agora:%d/%m/%Y %H:%M}\n"
    report+="Fonte: MET Norway, previsão por ponto; não é aviso oficial de tempo severo\n"
    report+="\n".join(f'{c["regiao"]}: {c["nome"]} {c["mi"]}° a {c["ma"]}° · {c["mm"]:g} mm' for c in cidades)
    saida.parent.mkdir(parents=True,exist_ok=True)
    doc={
      "tipo":"aviso","apresenta":"bia","validade":(agora+dt.timedelta(hours=4)).isoformat(),
      "titulo":titulo,"etiquetas":[f"AMANHÃ · {data.day:02d}/{data.month:02d}","DADOS REAIS · MET NORWAY"],
      "selo":"PREVISÃO RS","ceu":"nublado","trilha":True,
      "fonte":"MET Norway — previsão consultada no dia da renderização (CC BY 4.0)",
      "ticker":[f'{c["nome"].upper()}: {c["mi"]}° A {c["ma"]}° · {c["mm"]:g} MM' for c in cidades[:3]],
      "falas":falas,
      "legenda":f"🌦️ Previsão para {nome_dia}, {data:%d/%m/%Y} no Rio Grande do Sul.\n"+report+"\n\n@previsaors #PrevisaoRS #TempoRS"
    }
    saida.write_text(yaml.safe_dump(doc,allow_unicode=True,sort_keys=False,width=110),encoding="utf-8")
    saida.with_suffix(".txt").write_text(report+"\n",encoding="utf-8")
    print(report)
    print(f"Roteiro preparado: {saida}")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",default="output/snapshot.json")
    p.add_argument("--out",default="output/piloto_rs.yaml")
    a=p.parse_args()
    montar(json.loads(Path(a.snapshot).read_text(encoding="utf-8")),Path(a.out))
