"""Configuração central do radar e roteamento município -> canal."""
from __future__ import annotations

import csv
import os
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

REDE = Path(__file__).resolve().parents[1]           # scripts/rede
RAIZ = REDE.parents[1]                               # raiz do repositório
CONFIG = Path(os.environ.get('RADAR_CONFIG') or REDE / 'radar.yml')

UFS = dict(zip("11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53".split(),
               "RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF".split()))


def norm(s: str) -> str:
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().casefold()


@lru_cache(maxsize=None)
def carregar(caminho: str | None = None) -> dict:
    d = yaml.safe_load(Path(caminho or CONFIG).read_text(encoding='utf-8'))
    if d.get('modo') not in ('simulacao', 'publicacao'):
        raise ValueError('radar.yml: modo deve ser simulacao ou publicacao')
    return d


def modo() -> str:
    """Variável RADAR_MODO só pode RESTRINGIR (forçar simulação), nunca liberar."""
    if os.environ.get('RADAR_MODO') == 'simulacao':
        return 'simulacao'
    return carregar()['modo']


def canais_ativos() -> dict[str, dict]:
    return {k: v for k, v in carregar()['canais'].items() if v.get('ativo', True)}


def recorte(nome: str) -> set[str]:
    return {str(c) for c in carregar()['recortes'].get(nome, [])}


def canal_do_municipio(ibge: str) -> str | None:
    """Recorte próprio (ex.: Sul Fluminense) vence o canal da UF."""
    uf = UFS.get(str(ibge)[:2])
    ativos = canais_ativos()
    for nome, c in ativos.items():
        if c.get('recorte') and str(ibge) in recorte(c['recorte']):
            return nome
    for nome, c in ativos.items():
        if c['uf'] == uf and not c.get('recorte'):
            return nome
    return None


@lru_cache(maxsize=1)
def municipios() -> tuple[dict, ...]:
    with (REDE / 'municipios.csv').open(encoding='utf-8-sig') as f:
        return tuple(dict(r, uf=UFS[r['codigo_ibge'][:2]]) for r in csv.DictReader(f))


def municipios_monitorados() -> list[dict]:
    """TODOS os municípios das UFs atendidas, independente do rodízio diário."""
    return [dict(m, canal=canal_do_municipio(m['codigo_ibge'])) for m in municipios()
            if canal_do_municipio(m['codigo_ibge'])]


def limiares(uf: str | None = None, canal: str | None = None) -> list[tuple[int, float]]:
    cfg = carregar()['limiares']
    base = {int(x['horas']): float(x['mm']) for x in cfg['padrao']}
    ajustes = cfg.get('ajustes') or {}
    for chave in (uf, canal):
        for h, mm in (ajustes.get(chave) or {}).items():
            base[int(h)] = float(mm)
    return sorted(base.items())


def eventos() -> dict[str, list[str]]:
    return carregar()['eventos']
