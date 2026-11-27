"""Alternativa 100% Python (custo zero) quando não há crédito/LLM.

Extrai com regras simples o mesmo esquema do llm.py. É mais conservadora:
prefere deixar campo vazio a arriscar.
"""
from __future__ import annotations

import re

from . import config

MAI = "A-ZÁÉÍÓÚÂÊÔÃÕÇÜ"
PAL = rf"[{MAI}0-9][\w'’ºª-]*"
NOME = rf"{PAL}(?:\s+(?:de|da|do|dos|das|d')?\s*{PAL}){{0,4}}"
CORTE = re.compile(r'[.;:()\n]|\s(?:com|onde|que|após|apos|além|alem|entre|durante|até|ate|na|no|nas|nos|pela|pelo)\s')

PASSADO = ('transbord', 'alagou', 'alagaram', 'registrou', 'registrada', 'registrados', 'provocou',
           'atingiu', 'atingidos', 'atingidas', 'interditad', 'desaloj', 'desabrig', 'acolhid',
           'encaminhad', 'deslizamento', 'arrastad', 'destelh', 'caiu', 'cairam', 'morreu',
           'acionad', 'transborda', 'alaga ', 'atinge', 'interdita')
RISCO = ('alerta', 'previsao', 'previsto', 'pode ', 'podem ', 'possibilidade', 'risco', 'tendencia')

NUM = {'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6,
       'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'doze': 12}


def _lista_apos(texto: str, gatilho: str) -> list[str]:
    out = []
    for m in re.finditer(gatilho, texto, flags=re.I):
        trecho = CORTE.split(texto[m.end(): m.end() + 220])[0]
        for parte in re.split(r',\s*|\s+e\s+', trecho):
            parte = parte.strip(' "\'“”')
            if re.fullmatch(NOME, parte) and len(parte.split()) <= 5:
                out.append(parte)
    return out


def _numero(s: str) -> int | None:
    s = config.norm(s)
    return int(s) if s.isdigit() else NUM.get(s)


NEGACAO = re.compile(r'\b(nao|nem|sem|nenhum|nenhuma|descart\w*)\b[^.;]{0,45}$')


def _cita(n: str, termo: str) -> bool:
    """O termo aparece SEM negação logo antes ("não registrou transbordamento" não conta)."""
    i = n.find(termo)
    while i >= 0:
        if not NEGACAO.search(n[max(0, i - 60):i]):
            return True
        i = n.find(termo, i + 1)
    return False


def extrair(municipio: str, uf: str, evidencias: list[dict]) -> dict:
    textos = [f"{e.get('titulo', '')}. {e.get('trecho', '')}" for e in evidencias]
    tudo = '\n'.join(textos)
    n = config.norm(tudo)

    tipos = [t for t, ps in config.eventos().items() if any(_cita(n, p) for p in ps)]
    mm = [float(x.replace(',', '.')) for x in re.findall(r'(\d{1,3}(?:[.,]\d)?)\s*(?:mm\b|mil[ií]metros)', tudo)]

    rios = []
    for m in re.finditer(rf'\b[Rr]ios\s+({NOME})\s+e\s+({PAL}(?:\s+{PAL})?)', tudo):
        rios += [f'Rio {m.group(1)}', f'Rio {m.group(2)}']
    for m in re.finditer(rf'\b(Rio|Córrego|Corrego|Ribeirão|Riacho)\s+({NOME})', tudo):
        rios.append(f'{m.group(1)} {m.group(2)}')
    rios = [r for r in rios if config.norm(r) not in (config.norm('Rio ' + municipio),) or 'rio ' + config.norm(municipio) in n]

    bairros = _lista_apos(tudo, r'\bbairros?\s+(?:de\s+|do\s+|da\s+)?')
    bairros += _lista_apos(tudo, r'\blocalidades?\s+')
    vias = [m.group(0) for m in re.finditer(rf'\b(?:Rua|Avenida|Av\.|Estrada|Rodovia|Travessa|Ponte|Viaduto)\s+{NOME}', tudo)]
    vias += re.findall(r'\b(?:BR|RJ|SP|MG|PR|RS|BA|SC|ES|GO|DF)-\d{3}\b', tudo)
    apoio = [m.group(0) for m in re.finditer(rf'\b(?:Col[eé]gio|Escola|Gin[aá]sio|Igreja|Centro)\s+(?:Municipal\s+|Estadual\s+)?{NOME}', tudo)]

    acolhidos = None
    m = re.search(r'(\d+|\w+)\s+(?:moradores|pessoas|fam[ií]lias)\s+(?:foram\s+|precisaram\s+|chegaram\s+a\s+ser\s+)?'
                  r'(?:encaminhad|acolhid|desalojad|desabrigad|de abrigo|ir para)', tudo, re.I)
    if m:
        acolhidos = _numero(m.group(1))
    mortes = None
    m = re.search(r'(\d+|\w+)\s+(?:pessoas?\s+)?(?:morreram|mortos|mortes|morreu|óbitos?)', tudo, re.I)
    if m and _numero(m.group(1)):
        mortes = _numero(m.group(1))

    tels = re.findall(r'\b(?:199|193)\b', tudo) + re.findall(r'\(\d{2}\)\s?9?\d{4}-?\d{4}', tudo)
    servicos = []
    if any(p in n for p in config.eventos()['agua']):
        servicos.append('abastecimento de água')
    if any(p in n for p in config.eventos()['energia']):
        servicos.append('energia elétrica')
    orgaos = [o for o in ('Defesa Civil', 'Corpo de Bombeiros', 'INMET', 'Cemaden', 'CEMADEN-RJ', 'SEDEC-RJ',
                          'INEA', 'Prefeitura', 'Saae', 'Guarda Municipal') if config.norm(o) in n]

    periodo = ''
    m = re.search(r'entre a (noite|tarde|manh[ãa]|madrugada) d[eo] (\w+-feira)(?: \(\d+\))? e a (madrugada|manh[ãa]|tarde|noite)'
                  r' (?:desta |de |da )?(\w+-feira)', tudo, re.I)
    if m:
        periodo = f'{m.group(1)} de {m.group(2)} e a {m.group(3)} de {m.group(4)}'.lower()

    passado = sum(_cita(n, p) for p in PASSADO)
    risco = sum(p in n for p in RISCO)
    situacao = 'ocorrencia_confirmada' if passado >= 2 else ('risco_previsto' if risco else 'indefinido')

    def uniq(xs):
        vistos, out = set(), []
        for x in xs:
            k = config.norm(x)
            if k not in vistos and config.norm(municipio) != k:
                vistos.add(k)
                out.append(x)
        return out[:12]

    return {'municipio': municipio, 'uf': uf, 'tipo_principal': tipos[0] if tipos else '',
            'tipos': tipos, 'situacao': situacao, 'data_evento': '', 'periodo': periodo,
            # o valor mais citado (não o maior: a matéria pode citar a cidade vizinha)
            'chuva_mm': max(set(mm), key=lambda v: (mm.count(v), -v)) if mm else None,
            'chuvas_citadas_mm': sorted(set(mm)),
            'bairros': uniq(bairros), 'rios_corregos': uniq(rios), 'vias_interditadas': uniq(vias),
            'comunidades': [], 'desalojados_ou_acolhidos': acolhidos, 'mortes': mortes,
            'pontos_de_apoio': uniq(apoio), 'servicos_afetados': servicos, 'orientacoes': [],
            'telefones': list(dict.fromkeys(tels)), 'orgaos_citados': orgaos, 'evolucao': '',
            'contradicoes': [], '_modelo': 'extracao_python'}
