"""Fontes GRATUITAS do radar (nenhuma pede chave):

- IDAP / Defesa Civil (CAP, todos os municípios por geocódigo IBGE)
- INMET — avisos meteorológicos (RSS + CAP de cada aviso)
- Google Notícias RSS — imprensa regional, prefeituras e órgãos estaduais
- MET Norway — chuva PREVISTA por município (a fonte que a rede já usa;
  CC BY 4.0, exige crédito e User-Agent). Vira "risco previsto", nunca
  "ocorrência confirmada".

Toda resposta de fora passa por seguranca.limpar() antes de seguir adiante.
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from . import config, seguranca

sys.path.insert(0, str(config.REDE))
import monitor_defesa_civil_brasil as idap  # noqa: E402

UA = 'PrevisaoRadarRegional/1.0 github.com/pabloramoa-dev/previsao-modelo'
LIMITE = 30_000_000
INMET_RSS = 'https://apiprevmet3.inmet.gov.br/avisos/rss'


def baixar(url: str, timeout: int = 25, tentativas: int = 2) -> bytes:
    erro = None
    for i in range(tentativas):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA}), timeout=timeout) as r:
                b = r.read(LIMITE + 1)
            if len(b) > LIMITE:
                raise ValueError('resposta excessiva')
            return b
        except Exception as e:  # noqa: BLE001
            erro = e
            time.sleep(2 * (i + 1))
    raise erro


def xml_seguro(b: bytes):
    if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():
        raise ValueError('XML inseguro')
    return ET.fromstring(b)


# ------------------------------------------------------------ Defesa Civil
def alertas_defesa_civil(agora: datetime) -> list[dict]:
    dados = idap.parse(baixar(idap.FEED, timeout=45), agora)
    return dados['avisos']


# ------------------------------------------------------------ INMET
NS_CAP = '{urn:oasis:names:tc:emergency:cap:1.2}'


def alertas_inmet(agora: datetime, max_avisos: int = 60) -> list[dict]:
    """Avisos vigentes do INMET com municípios (geocódigo IBGE quando houver)."""
    raiz = xml_seguro(baixar(INMET_RSS))
    out = []
    for item in raiz.findall('.//item')[:max_avisos]:
        link = (item.findtext('link') or '').strip()
        titulo = seguranca.limpar(item.findtext('title'), 200)
        if not link.startswith('https://'):
            continue
        try:
            cap = xml_seguro(baixar(link, timeout=20, tentativas=1))
        except Exception:  # noqa: BLE001 - aviso isolado indisponível não derruba o radar
            continue
        for info in cap.iter(NS_CAP + 'info'):
            try:
                fim = datetime.fromisoformat((info.findtext(NS_CAP + 'expires') or '').strip())
            except ValueError:
                continue
            if fim <= agora:
                continue
            codigos = set()
            for geo in info.iter(NS_CAP + 'geocode'):
                for c in re.split(r'[,;\s]+', geo.findtext(NS_CAP + 'value') or ''):
                    if re.fullmatch(r'\d{7}', c) and c[:2] in config.UFS:
                        codigos.add(c)
            out.append({'orgao': 'INMET', 'evento': seguranca.limpar(info.findtext(NS_CAP + 'event'), 120) or titulo,
                        'severidade': (info.findtext(NS_CAP + 'severity') or '').strip(),
                        'fim': fim.isoformat(), 'ibge': sorted(codigos), 'fonte': link,
                        'descricao': seguranca.limpar(info.findtext(NS_CAP + 'description'), 600)})
            break
    return out


# ------------------------------------------------------------ Google Notícias
_ULTIMA_GN = [0.0]


def _baixar_google(url: str) -> bytes:
    """Google Notícias devolve 429 se pedirmos rápido demais: 1 pedido a cada 2,5 s
    e, no 429, espera 20 s e tenta de novo (até 3 vezes)."""
    for tentativa in range(3):
        espera = _ULTIMA_GN[0] + 2.5 - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        _ULTIMA_GN[0] = time.monotonic()
        try:
            return baixar(url, tentativas=1)
        except Exception as e:  # noqa: BLE001
            if getattr(e, 'code', None) != 429 or tentativa == 2:
                raise
            time.sleep(20 * (tentativa + 1))
    raise RuntimeError('inalcançável')


def google_noticias(consulta: str, agora: datetime, janela_h: int = 36, maximo: int = 15) -> list[dict]:
    url = 'https://news.google.com/rss/search?' + urlencode(
        {'q': consulta, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'})
    raiz = xml_seguro(_baixar_google(url))
    out = []
    for item in raiz.findall('.//item'):
        try:
            quando = parsedate_to_datetime(item.findtext('pubDate'))
        except (TypeError, ValueError):
            continue
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        if not agora - timedelta(hours=janela_h) <= quando <= agora + timedelta(minutes=10):
            continue
        src = item.find('source')
        veiculo = seguranca.limpar(src.text if src is not None else '', 80)
        site = seguranca.dominio(src.get('url', '')) if src is not None else ''
        titulo = seguranca.limpar(item.findtext('title'), 300)
        if veiculo and titulo.endswith(' - ' + veiculo):
            titulo = titulo[: -len(veiculo) - 3]
        out.append({'titulo': titulo, 'url': (item.findtext('link') or '').strip(), 'veiculo': veiculo,
                    'dominio': site, 'publicado': quando.isoformat(), 'trecho': '',
                    'origem': 'google_noticias', 'oficial': seguranca.eh_oficial(site)})
        if len(out) >= maximo:
            break
    return out


def termos_eventos() -> str:
    return '(enchente OR alagamento OR transbordamento OR deslizamento OR enxurrada OR temporal OR granizo OR vendaval OR tornado OR ciclone OR "Defesa Civil")'


def consulta_municipio(cidade: str, uf: str) -> str:
    return f'"{cidade}" {uf} {termos_eventos()} when:2d'


def consultas_regionais(nome_uf: str) -> list[str]:
    """Varredura barata por estado: pega ocorrência que ainda não tem alerta."""
    return [f'"{nome_uf}" {termos_eventos()} when:1d',
            f'"Defesa Civil" "{nome_uf}" (chuva OR temporal OR alerta) when:1d']


# ------------------------------------------------------------ MET Norway (chuva prevista)
MET = 'https://api.met.no/weatherapi/locationforecast/2.0/compact'


def chuva_prevista_met(lat: float, lon: float) -> list[tuple[datetime, float, int]]:
    """[(início, mm, horas)] — usa next_1_hours e, depois, next_6_hours."""
    import json
    url = f'{MET}?lat={lat:.2f}&lon={lon:.2f}'   # met.no pede no máx. 4 casas; 2 = grade de ~1 km, cacheável
    d = json.loads(baixar(url, timeout=20))
    out, fim_coberto = [], None
    for p in d['properties']['timeseries']:
        t = datetime.fromisoformat(p['time'].replace('Z', '+00:00'))
        if fim_coberto and t < fim_coberto:
            continue
        for chave, h in (('next_1_hours', 1), ('next_6_hours', 6)):
            bloco = p['data'].get(chave)
            if bloco and 'precipitation_amount' in bloco.get('details', {}):
                out.append((t, float(bloco['details']['precipitation_amount']), h))
                fim_coberto = t + timedelta(hours=h)
                break
    return out


def acumulados(serie, agora: datetime, janelas=(1, 3, 24, 48, 72)) -> dict[int, float]:
    res = {}
    for j in janelas:
        lim = agora + timedelta(hours=j)
        tot = 0.0
        for t, mm, h in serie:
            if t >= lim or t + timedelta(hours=h) <= agora:
                continue
            ini, fim = max(t, agora), min(t + timedelta(hours=h), lim)
            tot += mm * (fim - ini).total_seconds() / (h * 3600)
        res[j] = round(tot, 1)
    return res


def gatilhos(acum: dict[int, float], limiares: list[tuple[int, float]]) -> list[str]:
    return [f'{h}h >= {mm:g} mm' for h, mm in limiares if acum.get(h, 0) >= mm]


def varrer_chuva(municipios: list[dict], agora: datetime, cache, trabalhadores: int = 6) -> tuple[list[dict], dict]:
    """Uma consulta por célula de ~0,25° (municípios vizinhos compartilham)."""
    celulas: dict[tuple, list[dict]] = {}
    for m in municipios:
        k = (round(float(m['latitude']) * 4) / 4, round(float(m['longitude']) * 4) / 4)
        celulas.setdefault(k, []).append(m)

    def uma(k):
        em_cache = cache.obter('met', k)
        if em_cache is not None:
            return k, [(datetime.fromisoformat(t), mm, h) for t, mm, h in em_cache], None
        try:
            serie = chuva_prevista_met(*k)
        except Exception as e:  # noqa: BLE001
            return k, None, str(e)
        cache.guardar([(t.isoformat(), mm, h) for t, mm, h in serie], 3600, 'met', k)
        return k, serie, None

    alertas, falhas = [], 0
    with ThreadPoolExecutor(trabalhadores) as ex:
        for k, serie, erro in ex.map(uma, celulas):
            if serie is None:
                falhas += 1
                continue
            acum = acumulados(serie, agora)
            for m in celulas[k]:
                g = gatilhos(acum, config.limiares(m['uf'], m['canal']))
                if g:
                    alertas.append({'ibge': m['codigo_ibge'], 'cidade': m['nome'], 'uf': m['uf'],
                                    'canal': m['canal'], 'acumulado_previsto_mm': acum, 'gatilhos': g,
                                    'fonte': 'MET Norway (previsão)'})
    return alertas, {'celulas': len(celulas), 'falhas': falhas}
