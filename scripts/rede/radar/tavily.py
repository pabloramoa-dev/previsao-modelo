"""Tavily: SÓ para aprofundar uma ocorrência já detectada (nunca para varredura).

Busca básica = 1 crédito. Cada chamada passa por Cotas.reservar() e pelo cache;
sem chave, sem cota ou com erro, devolve [] e o radar segue só com RSS.
"""
from __future__ import annotations

import json
import os
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

from . import armazem, config, seguranca

URL = 'https://api.tavily.com/search'


def _data_iso(valor) -> str:
    """Tavily manda a data no formato de e-mail (RFC 2822); o radar usa ISO 8601."""
    if not valor:
        return ''
    try:
        return parsedate_to_datetime(str(valor)).isoformat()
    except (TypeError, ValueError):
        return str(valor)[:40]


def disponivel() -> bool:
    return bool(os.environ.get('TAVILY_API_KEY'))


def pesquisar(consulta: str, cotas: armazem.Cotas, cache: armazem.Cache, dias: int = 2,
              maximo: int = 8) -> tuple[list[dict], str]:
    """Devolve (resultados, situação). Situação: cache | ok | sem_chave | sem_cota | erro:..."""
    em_cache = cache.obter('tavily', consulta, dias)
    if em_cache is not None:
        return em_cache, 'cache'
    if not disponivel():
        return [], 'sem_chave'
    try:
        cotas.reservar('tavily', 1)
    except armazem.CotaEsgotada:
        return [], 'sem_cota'
    corpo = json.dumps({'query': consulta[:380], 'topic': 'news', 'days': dias, 'search_depth': 'basic',
                        'max_results': maximo, 'include_answer': False,
                        'include_raw_content': False}).encode()
    req = Request(URL, data=corpo, method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': f'Bearer {os.environ["TAVILY_API_KEY"]}'})
    try:
        with urlopen(req, timeout=40) as r:
            d = json.loads(r.read(5_000_000))
    except Exception as e:  # noqa: BLE001 - nunca imprimir cabeçalhos (contêm a chave)
        if getattr(e, 'code', None) in (401, 403, 429, 432, 433):
            pass  # chamada recusada: crédito não consumido do lado deles, mas mantemos a reserva (conservador)
        return [], f'erro:{type(e).__name__}:{getattr(e, "code", "")}'
    out = []
    for x in d.get('results', []):
        url = str(x.get('url', ''))
        if not seguranca.url_segura(url):
            continue
        dom = seguranca.dominio(url)
        out.append({'titulo': seguranca.limpar(x.get('title'), 300), 'url': url, 'veiculo': dom,
                    'dominio': dom, 'publicado': _data_iso(x.get('published_date')),
                    'trecho': seguranca.limpar(x.get('content'), 1200), 'origem': 'tavily',
                    'oficial': seguranca.eh_oficial(dom)})
    ttl = config.carregar()['investigacao']['cache_tavily_horas'] * 3600
    cache.guardar(out, ttl, 'tavily', consulta, dias)
    return out, 'ok'
