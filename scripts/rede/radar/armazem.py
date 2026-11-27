"""Estado persistente do radar: cache, cotas e ocorrências.

Fica em RADAR_ESTADO (padrão estado_radar/), que o workflow guarda entre
execuções com actions/cache. Tudo JSON, escrito de forma atômica.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config


def pasta() -> Path:
    p = Path(os.environ.get('RADAR_ESTADO') or 'estado_radar')
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ler(nome: str, padrao):
    f = pasta() / nome
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def _gravar(nome: str, dados) -> None:
    f = pasta() / nome
    tmp = f.with_suffix('.tmp')
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    tmp.replace(f)


def chave(*partes) -> str:
    bruto = '|'.join(config.norm(' '.join(str(p).split())) for p in partes)
    return hashlib.sha256(bruto.encode()).hexdigest()[:24]


# ----------------------------------------------------------------- cache
class Cache:
    """Consulta igual (normalizada) dentro do TTL não sai de novo: zero crédito."""

    def __init__(self):
        self.d = _ler('cache.json', {})
        self.acertos = 0
        agora = time.time()
        self.d = {k: v for k, v in self.d.items() if v.get('expira', 0) > agora}

    def obter(self, *partes):
        v = self.d.get(chave(*partes))
        if v and v['expira'] > time.time():
            self.acertos += 1
            return v['valor']
        return None

    def guardar(self, valor, ttl_s: float, *partes):
        self.d[chave(*partes)] = {'expira': time.time() + ttl_s, 'valor': valor}
        return valor

    def salvar(self):
        _gravar('cache.json', self.d)


# ----------------------------------------------------------------- cotas
class CotaEsgotada(RuntimeError):
    pass


class Cotas:
    """Controle centralizado de consumo das APIs. Antes de gastar: reservar()."""

    def __init__(self, agora: datetime | None = None):
        self.cfg = config.carregar()['cotas']
        self.d = _ler('cotas.json', {})
        agora = agora or datetime.now(timezone.utc)
        self.mes, self.dia = agora.strftime('%Y-%m'), agora.strftime('%Y-%m-%d')
        self.execucao: dict[str, int] = {}
        self.prioridade = False

    def usado(self, api: str, periodo: str) -> int:
        return int(self.d.get(api, {}).get(periodo, 0))

    def _limites(self, api):
        c = self.cfg[api]
        if api == 'tavily':
            por_exec = c['teto_prioridade'] if self.prioridade else c['teto_por_execucao']
            return [(self.mes, c['teto_mensal'])], por_exec
        return [(self.dia, c['teto_diario'])], c['teto_por_execucao']

    def disponivel(self, api: str, n: int = 1) -> bool:
        periodos, por_exec = self._limites(api)
        if self.execucao.get(api, 0) + n > por_exec:
            return False
        return all(self.usado(api, p) + n <= teto for p, teto in periodos)

    def reservar(self, api: str, n: int = 1) -> None:
        if not self.disponivel(api, n):
            raise CotaEsgotada(api)
        periodos, _ = self._limites(api)
        for p, _t in periodos:
            self.d.setdefault(api, {})[p] = self.usado(api, p) + n
        self.execucao[api] = self.execucao.get(api, 0) + n

    def devolver(self, api: str, n: int = 1) -> None:
        """Chamada que falhou antes de chegar à API não conta."""
        periodos, _ = self._limites(api)
        for p, _t in periodos:
            self.d.setdefault(api, {})[p] = max(0, self.usado(api, p) - n)
        self.execucao[api] = max(0, self.execucao.get(api, 0) - n)

    def resumo(self) -> dict:
        t, o = self.cfg['tavily'], self.cfg['openrouter']
        return {
            'tavily': {'mes': self.mes, 'usado_mes': self.usado('tavily', self.mes),
                       'teto_mes': t['teto_mensal'], 'franquia_mes': t['franquia_mensal'],
                       'nesta_execucao': self.execucao.get('tavily', 0)},
            'openrouter': {'dia': self.dia, 'usado_dia': self.usado('openrouter', self.dia),
                           'teto_dia': o['teto_diario'], 'franquia_dia': o['franquia_diaria'],
                           'nesta_execucao': self.execucao.get('openrouter', 0)},
        }

    def salvar(self):
        # guarda só os últimos 3 meses / 40 dias
        for api, per in self.d.items():
            for k in sorted(per)[:-45]:
                per.pop(k, None)
        _gravar('cotas.json', self.d)


# ----------------------------------------------------------------- ocorrências
class Ocorrencias:
    """Ocorrências em andamento + o que já foi produzido (anti-duplicidade)."""

    def __init__(self):
        self.d = _ler('ocorrencias.json', {'ativas': {}, 'edicoes': {}})

    @staticmethod
    def id_ocorrencia(ibge: str, tipo: str, data_local: str) -> str:
        return f'{ibge}-{tipo}-{data_local}'

    def ativa(self, oid: str) -> dict | None:
        return self.d['ativas'].get(oid)

    def atualizar(self, oid: str, registro: dict) -> None:
        self.d['ativas'][oid] = registro

    def fatos_ja_publicados(self, oid: str) -> set[str]:
        return set(self.d['edicoes'].get(oid, {}).get('fatos', []))

    # Uma edição só conta como feita depois que o vídeo foi renderizado e
    # conferido (artifact "edicao-ok-<id>" do job de edição). Até lá fica
    # pendente; se o render falhar, a pendência vence e a próxima execução
    # tenta de novo, em vez de a ocorrência ficar travada como "duplicada".
    def em_producao(self, oid: str) -> bool:
        return oid in self.d.setdefault('pendentes', {})

    def registrar_pendente(self, oid: str, fatos: set[str], arquivo: str, quando: str) -> None:
        self.d.setdefault('pendentes', {})[oid] = {'fatos': sorted(fatos), 'arquivo': arquivo, 'quando': quando}

    def registrar_edicao(self, oid: str, fatos: set[str], arquivo: str, quando: str) -> None:
        e = self.d['edicoes'].setdefault(oid, {'fatos': [], 'arquivos': []})
        e['fatos'] = sorted(set(e['fatos']) | set(fatos))
        e['arquivos'].append({'arquivo': arquivo, 'quando': quando})

    def resolver_pendentes(self, agora: datetime, confirmadas: set[str], horas: float = 3) -> dict:
        """Confirma as que renderizaram; descarta as vencidas sem confirmação."""
        res = {'confirmadas': [], 'vencidas': []}
        for oid, p in list(self.d.setdefault('pendentes', {}).items()):
            if oid in confirmadas:
                self.registrar_edicao(oid, set(p['fatos']), p['arquivo'], p['quando'])
                self.d['pendentes'].pop(oid)
                res['confirmadas'].append(oid)
            elif (agora - datetime.fromisoformat(p['quando'])).total_seconds() > horas * 3600:
                self.d['pendentes'].pop(oid)
                res['vencidas'].append(oid)
        return res

    def encerrar_antigas(self, agora: datetime, horas: int = 96) -> None:
        for oid, r in list(self.d['ativas'].items()):
            try:
                visto = datetime.fromisoformat(r['ultima_evidencia'])
            except (KeyError, ValueError):
                continue
            if (agora - visto).total_seconds() > horas * 3600:
                self.d['ativas'].pop(oid)

    def salvar(self):
        _gravar('ocorrencias.json', self.d)
