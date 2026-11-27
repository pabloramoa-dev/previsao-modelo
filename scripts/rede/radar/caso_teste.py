"""Reexecuta um caso histórico OFFLINE (sem rede, sem créditos).

    python scripts/rede/radar_regional.py --caso tests/fixtures/radar/barra_mansa_2026-11-26.json

Serve para provar detecção, pesquisa, bairros/rios, validação, roteiro,
controle de cota (Tavily simulado conta crédito) e bloqueio de duplicidade
(rodando duas vezes, a segunda não gera nova edição).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import armazem, config, motor, seguranca, validacao


class FontesDoCaso:
    def __init__(self, caso: dict, cache):
        self.c, self.cache, self.erros = caso, cache, []
        self.consultas_tavily = 0

    def alertas_defesa_civil(self):
        return self.c.get('alertas', [])

    def alertas_inmet(self):
        return []

    def noticias(self, consulta):
        out = []
        for cidade, itens in self.c.get('rss', {}).items():
            if config.norm(cidade) in config.norm(consulta):
                out += [dict(i, trecho='', origem='google_noticias',
                             oficial=False) for i in itens]
        return out

    def chuva(self, municipios):
        return [], {'celulas': 0, 'falhas': 0, 'nota': 'caso histórico: sem previsão'}

    def tavily(self, consulta, cotas):
        em_cache = self.cache.obter('tavily', consulta, 2)
        if em_cache is not None:
            return em_cache, 'cache'
        try:
            cotas.reservar('tavily', 1)
        except armazem.CotaEsgotada:
            return [], 'sem_cota'
        self.consultas_tavily += 1
        res = [dict(i, trecho=seguranca.limpar(i.get('trecho'), 1200), origem='tavily', oficial=False)
               for i in self.c.get('tavily', [])]
        return self.cache.guardar(res, 3600, 'tavily', consulta, 2), 'ok(simulado)'


def rodar(caminho: str, saida: Path = Path('output/caso_teste')) -> dict:
    caso = json.loads(Path(caminho).read_text(encoding='utf-8'))
    agora = datetime.fromisoformat(caso['agora'])
    cache = armazem.Cache()
    src = FontesDoCaso(caso, cache)
    rel = motor.executar('profunda', agora=agora, src=src, saida=saida, cache=cache)
    return rel, caso.get('esperado', {}), src


def conferir(rel: dict, esperado: dict) -> list[str]:
    """Lista de falhas (vazia = passou)."""
    falhas = []
    inv = [i for i in rel['investigados'] if i['fatos']]
    if not inv:
        return ['nenhuma ocorrência investigada']
    i = inv[0]
    f = i['fatos']
    if i['classificacao']['status'] != esperado.get('status'):
        falhas.append(f"status {i['classificacao']['status']} != {esperado.get('status')}")
    rios = ' '.join(f['rios_corregos'])
    for r in esperado.get('rios', []):
        if r not in rios:
            falhas.append(f'rio ausente: {r}')
    for b in esperado.get('bairros_incluem', []):
        if b not in f['bairros']:
            falhas.append(f'bairro ausente: {b}')
    if esperado.get('chuva_mm') and f.get('chuva_mm') != esperado['chuva_mm']:
        falhas.append(f"chuva {f.get('chuva_mm')} != {esperado['chuva_mm']}")
    if esperado.get('acolhidos') and f.get('desalojados_ou_acolhidos') != esperado['acolhidos']:
        falhas.append(f"acolhidos {f.get('desalojados_ou_acolhidos')} != {esperado['acolhidos']}")
    antigas = sum(v for k, v in i['descartadas'].items() if k.startswith('antiga'))
    if antigas < esperado.get('descartar_antigas', 0):
        falhas.append(f'notícias antigas descartadas: {antigas}')
    if any('[removido]' not in e.get('titulo', '') and 'ignore as instru' in validacao.config.norm(e.get('titulo', ''))
           for e in i['evidencias']):
        falhas.append('injeção não neutralizada')
    return falhas
