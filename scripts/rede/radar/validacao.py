"""Segurança editorial: o que pode virar edição extraordinária.

Regras (scripts/rede/radar.yml -> editorial):
- evidência só conta se citar o município E um evento, e for recente;
- notícia antiga (data fora da janela ou ano antigo no endereço) é descartada;
- todo bairro/rio/via/ponto de apoio precisa aparecer escrito nas fontes;
- telefone só se for oficial nacional ou estiver nas fontes;
- "confirmada" = fato ocorrido + (>=1 fonte oficial OU >=2 veículos independentes);
- alerta/previsão sem fato ocorrido = risco (não vira edição de ocorrência);
- contradição relevante (vítimas, números muito diferentes) BLOQUEIA;
- nova edição da mesma ocorrência só com fatos novos relevantes.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import config, seguranca

AGREGADORES = ('msn.com', 'yahoo.com', 'news.google.com', 'flipboard.com', 'gigantum.net', 'mixvale.com.br',
               'brasilemfolhas.com.br')


def dominio_raiz(d: str) -> str:
    partes = (d or '').casefold().split('.')
    if len(partes) >= 3 and partes[-1] == 'br' and partes[-2] in ('com', 'gov', 'org', 'net', 'leg', 'jus', 'edu'):
        return '.'.join(partes[-3:])
    return '.'.join(partes[-2:])


def _quando(e) -> datetime | None:
    try:
        return datetime.fromisoformat(str(e.get('publicado', '')).replace('Z', '+00:00'))
    except ValueError:
        return None


def evidencia_relevante(e: dict, cidade: str, agora: datetime, janela_h: int) -> tuple[bool, str]:
    txt = config.norm(f"{e.get('titulo', '')} {e.get('trecho', '')}")
    if config.norm(cidade) not in txt:
        return False, 'nao_cita_municipio'
    if not any(p in txt for ps in config.eventos().values() for p in ps) and 'chuva' not in txt:
        return False, 'sem_evento'
    q = _quando(e)
    if q is not None:
        if q.tzinfo is None:
            q = q.replace(tzinfo=agora.tzinfo)
        if q < agora - timedelta(hours=janela_h):
            return False, 'antiga'
        if q > agora + timedelta(minutes=10):
            return False, 'data_futura'
    anos = [int(a) for a in re.findall(r'/(20\d\d)/', str(e.get('url', '')))]
    if anos and max(anos) < agora.year:
        return False, 'antiga_pela_url'
    if q is None and not e.get('oficial'):
        return False, 'sem_data'
    return True, 'ok'


def ancorar(fatos: dict, evidencias: list[dict]) -> tuple[dict, list[str]]:
    texto = ' '.join(f"{e.get('titulo', '')} {e.get('trecho', '')}" for e in evidencias)
    tn = config.norm(texto)
    limpo, descartes = dict(fatos), []
    for campo in ('bairros', 'rios_corregos', 'vias_interditadas', 'comunidades', 'pontos_de_apoio'):
        ok = []
        for v in fatos.get(campo) or []:
            v = seguranca.limpar(v, 80)
            nucleo = re.sub(r'^(rio|corrego|córrego|ribeirao|ribeirão|bairro)\s+', '', v, flags=re.I)
            if seguranca.ancorado(nucleo, tn):
                ok.append(v)
            else:
                descartes.append(f'{campo}:{v}')
        limpo[campo] = list(dict.fromkeys(ok))[:10]
    limpo['telefones'] = seguranca.telefones_validos(fatos.get('telefones'), texto)
    for campo in ('chuva_mm', 'desalojados_ou_acolhidos', 'mortes'):
        v = fatos.get(campo)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            limpo[campo] = None
            continue
        rep = f'{v:g}'
        if not re.search(rf'(?<![\d,.]){re.escape(rep)}(?![\d])', texto) and not (v == 1 and re.search(r'\bum[a]?\b', tn)):
            descartes.append(f'{campo}:{rep}')
            limpo[campo] = None
        else:
            limpo[campo] = int(v) if v.is_integer() else v
    for campo in ('orientacoes', 'orgaos_citados', 'servicos_afetados', 'tipos', 'contradicoes'):
        limpo[campo] = [seguranca.limpar(x, 160) for x in (fatos.get(campo) or [])][:8]
    for campo in ('municipio', 'uf', 'tipo_principal', 'situacao', 'data_evento', 'periodo', 'evolucao', '_modelo'):
        limpo[campo] = seguranca.limpar(fatos.get(campo, ''), 200)
    palavras = [p for p in re.findall(r'\w{4,}', config.norm(limpo['periodo']))]
    if palavras and not all(p in tn for p in palavras):
        descartes.append(f"periodo:{limpo['periodo']}")
        limpo['periodo'] = ''
    return limpo, descartes


def mesclar(llm: dict | None, py: dict) -> dict:
    """LLM manda; o que ele deixou vazio, a extração Python completa."""
    if not llm:
        return py
    out = dict(py)
    for k, v in llm.items():
        if v not in (None, '', [], {}):
            out[k] = v
    for k in ('bairros', 'rios_corregos', 'vias_interditadas', 'pontos_de_apoio', 'telefones', 'tipos'):
        out[k] = list(dict.fromkeys(list(llm.get(k) or []) + list(py.get(k) or [])))
    out['_modelo'] = llm.get('_modelo', '') + '+python'
    out['_python'] = {'mortes': py.get('mortes'), 'chuvas_citadas_mm': py.get('chuvas_citadas_mm')}
    return out


def contradicoes(fatos: dict) -> list[str]:
    c = list(fatos.get('contradicoes') or [])
    py = fatos.get('_python') or {}
    if py.get('mortes') is not None and fatos.get('mortes') is not None and py['mortes'] != fatos['mortes']:
        c.append(f"vítimas divergentes ({py['mortes']} x {fatos['mortes']})")
    return c


def bloqueante(lista: list[str]) -> bool:
    if not config.carregar()['editorial']['bloquear_se_contraditorio']:
        return False
    chaves = ('vitima', 'morte', 'mort', 'obito', 'ferid', 'data', 'municipio', 'cidade', 'antig')
    return any(any(k in config.norm(x) for k in chaves) for x in lista)


def classificar(candidato: dict, evidencias: list[dict], fatos: dict, agora: datetime) -> dict:
    ed = config.carregar()['editorial']
    oficiais = [e for e in evidencias if e.get('oficial')]
    raizes = {dominio_raiz(e.get('dominio') or seguranca.dominio(e.get('url', ''))) for e in evidencias
              if not e.get('oficial')}
    raizes = {r for r in raizes if r and r not in AGREGADORES}
    alertas_oficiais = [a for a in candidato.get('alertas', []) if a.get('severidade') in ('Moderate', 'Severe', 'Extreme')]
    ocorreu = fatos.get('situacao') == 'ocorrencia_confirmada'
    contra = contradicoes(fatos)

    if contra and bloqueante(contra):
        status = 'bloqueada_contradicao'
    elif ocorreu and (len(oficiais) >= ed['confirmacao']['fontes_oficiais_min']
                      or len(raizes) >= ed['confirmacao']['veiculos_independentes_min']):
        status = 'confirmada'
    elif ocorreu and evidencias:
        status = 'em_verificacao'
    elif alertas_oficiais:
        status = 'risco_oficial'
    elif candidato.get('chuva_prevista'):
        status = 'risco_previsto'
    else:
        status = 'sem_evidencia'

    mm = fatos.get('chuva_mm') or 0
    prioridade = 'maxima' if (
        (mm and float(mm) > config.carregar()['limiares']['prioridade_maxima_mm_24h'])
        or any(a.get('severidade') in ('Severe', 'Extreme') for a in candidato.get('alertas', []))
        or (status == 'confirmada' and (fatos.get('mortes') or fatos.get('desalojados_ou_acolhidos')))
    ) else ('alta' if status == 'confirmada' else 'normal')
    return {'status': status, 'prioridade': prioridade, 'fontes_oficiais': len(oficiais),
            'veiculos_independentes': sorted(raizes), 'contradicoes': contra,
            'elegivel_publicacao': status == 'confirmada'}


def fatos_relevantes(fatos: dict) -> set[str]:
    s = {f'tipo:{t}' for t in fatos.get('tipos') or []}
    s |= {f'bairro:{config.norm(b)}' for b in fatos.get('bairros') or []}
    s |= {f'rio:{config.norm(r)}' for r in fatos.get('rios_corregos') or []}
    s |= {f'via:{config.norm(v)}' for v in fatos.get('vias_interditadas') or []}
    for k in ('desalojados_ou_acolhidos', 'mortes'):
        if fatos.get(k):
            s.add(f'{k}:{fatos[k]}')
    if fatos.get('chuva_mm'):
        s.add(f'mm:{int(float(fatos["chuva_mm"]) // 20 * 20)}')   # faixa de 20 mm
    return s


def decisao_edicao(oid: str, fatos: dict, classif: dict, ocorrencias) -> tuple[bool, str, set[str]]:
    novos = fatos_relevantes(fatos) - ocorrencias.fatos_ja_publicados(oid)
    if not classif['elegivel_publicacao']:
        return False, f"não elegível ({classif['status']})", novos
    if not ocorrencias.fatos_ja_publicados(oid):
        return True, 'primeira edição', novos
    minimo = config.carregar()['editorial']['atualizacao_minima']
    if len(novos) >= minimo:
        return True, f'atualização: {len(novos)} fatos novos', novos
    return False, 'duplicada: sem fatos novos relevantes', novos
