"""Uma execução do radar.

  leve      (a cada 15 min): só alertas oficiais (Defesa Civil + INMET). Alerta
            grave novo -> investigação prioritária na hora.
  profunda  (05, 08, 11, 14, 17, 20, 23h): alertas + varredura RSS por estado +
            chuva prevista (MET Norway) + investigação hiperlocal dos candidatos.

Fluxo de uma investigação (do mais barato para o mais caro):
  1. Google Notícias RSS do município (grátis, com cache)
  2. Tavily SÓ se faltar confirmação ou detalhe (bairros/rios) — com teto
  3. OpenRouter :free para interpretar; sem ele, extração em Python
  4. validação editorial -> roteiro -> fila de edição (simulação por padrão)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import armazem, config, extracao, fontes, llm, roteiro, tavily, validacao

FUSO = ZoneInfo('America/Sao_Paulo')
STOP_NOMES = {'serra', 'bonito', 'planalto', 'vitoria', 'esperanca', 'progresso', 'uniao', 'triunfo', 'cristal',
              'alegre', 'central', 'jardim', 'brasilia', 'colorado', 'bandeirantes', 'cascavel', 'natal', 'sao paulo',
              'rio de janeiro', 'bahia', 'parana', 'goias', 'para', 'sul', 'norte', 'pedras', 'pontal', 'castro',
              'campo grande', 'santa maria', 'amparo', 'sumidouro', 'sapucaia', 'ipe', 'nova friburgo'}


class FontesAoVivo:
    def __init__(self, cache, agora):
        self.cache, self.agora, self.erros = cache, agora, []
        self.janela = config.carregar()['investigacao']['janela_noticia_horas']

    def _tentar(self, nome, fn, padrao):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - fonte fora do ar não derruba o radar
            self.erros.append({'fonte': nome, 'erro': f'{type(e).__name__}: {str(e)[:160]}'})
            return padrao

    def alertas_defesa_civil(self):
        return self._tentar('IDAP/Defesa Civil', lambda: fontes.alertas_defesa_civil(self.agora), [])

    def alertas_inmet(self):
        return self._tentar('INMET', lambda: fontes.alertas_inmet(self.agora), [])

    def noticias(self, consulta):
        c = self.cache.obter('rss', consulta)
        if c is not None:
            return c
        r = self._tentar('Google Notícias', lambda: fontes.google_noticias(consulta, self.agora, self.janela), None)
        if r is None:
            return []
        ttl = config.carregar()['investigacao']['cache_rss_minutos'] * 60
        return self.cache.guardar(r, ttl, 'rss', consulta)

    def chuva(self, municipios):
        r = self._tentar('MET Norway', lambda: fontes.varrer_chuva(municipios, self.agora, self.cache), ([], {}))
        return r

    def tavily(self, consulta, cotas):
        return tavily.pesquisar(consulta, cotas, self.cache)


# ------------------------------------------------------------------ candidatos
def _gazetteer(uf: str):
    ms = [m for m in config.municipios_monitorados() if m['uf'] == uf]
    ms = [m for m in ms if config.norm(m['nome']) not in STOP_NOMES and len(m['nome']) >= 5]
    return sorted(ms, key=lambda m: -len(m['nome']))


def municipio_no_titulo(titulo: str, uf: str):
    t = f' {config.norm(titulo)} '
    for m in _gazetteer(uf):
        n = config.norm(m['nome'])
        if re.search(rf'(?<![a-z]){re.escape(n)}(?![a-z])', t):
            return m
    return None


def juntar_candidatos(alertas, chuvas, regionais) -> dict[str, dict]:
    idx = {m['codigo_ibge']: m for m in config.municipios_monitorados()}
    cand: dict[str, dict] = {}

    def pegar(ibge):
        m = idx[ibge]
        return cand.setdefault(ibge, {'ibge': ibge, 'cidade': m['nome'], 'uf': m['uf'], 'canal': m['canal'],
                                      'alertas': [], 'chuva_prevista': None, 'pistas': [], 'motivos': []})
    for a in alertas:
        for c in a.get('ibge', []):
            if c in idx:
                k = pegar(c)
                k['alertas'].append({x: a.get(x) for x in ('orgao', 'evento', 'severidade', 'fim', 'fonte')})
                k['motivos'].append(f"alerta {a.get('orgao', '')}: {a.get('evento', '')} ({a.get('severidade', '')})")
    for ch in chuvas:
        k = pegar(ch['ibge'])
        k['chuva_prevista'] = ch
        k['motivos'].append('chuva prevista: ' + ', '.join(ch['gatilhos']))
    for p in regionais:
        k = pegar(p['ibge'])
        k['pistas'].append(p['noticia'])
        k['motivos'].append('notícia regional: ' + p['noticia']['titulo'][:90])
    return cand


def pontuar(c: dict) -> float:
    sev = {'Extreme': 40, 'Severe': 25, 'Moderate': 10, 'Minor': 3}
    s = max([sev.get(a.get('severidade'), 0) for a in c['alertas']] or [0])
    s += 15 * len(c['pistas'])
    if c['chuva_prevista']:
        s += 5 * len(c['chuva_prevista']['gatilhos'])
        if c['chuva_prevista']['acumulado_previsto_mm'].get(24, 0) > config.carregar()['limiares']['prioridade_maxima_mm_24h']:
            s += 30
    return s


# ------------------------------------------------------------------ investigação
def investigar(c: dict, src, cotas, cache, agora: datetime) -> dict:
    inv = config.carregar()['investigacao']
    janela = inv['janela_noticia_horas']
    ev = list(c['pistas'])
    ev += src.noticias(fontes.consulta_municipio(c['cidade'], c['uf']))
    ev += src.noticias(f'"{c["cidade"]}" "Defesa Civil" when:2d')
    rel, descartadas = [], {}
    vistos = set()
    for e in ev:
        k = (e.get('url'), config.norm(e.get('titulo', ''))[:80])
        if k in vistos:
            continue
        vistos.add(k)
        ok, motivo = validacao.evidencia_relevante(e, c['cidade'], agora, janela)
        if ok:
            rel.append(e)
        else:
            descartadas[motivo] = descartadas.get(motivo, 0) + 1

    py = extracao.extrair(c['cidade'], c['uf'], rel)
    raizes = {validacao.dominio_raiz(e.get('dominio', '')) for e in rel if not e.get('oficial')}
    precisa_aprofundar = rel and (len(raizes) < 2 or not py['bairros'] or not py['rios_corregos'])
    situacao_tavily = 'nao_necessario'
    if precisa_aprofundar or (c['alertas'] and not rel):
        q = f'{c["cidade"]} {c["uf"]} chuva Defesa Civil bairros atingidos rio ocorrências'
        extra, situacao_tavily = src.tavily(q, cotas)
        por_url = {x.get('url'): x for x in rel}
        for e in extra:
            ok, motivo = validacao.evidencia_relevante(e, c['cidade'], agora, janela)
            if not ok:
                descartadas[motivo] = descartadas.get(motivo, 0) + 1
            elif e.get('url') in por_url:          # mesma matéria: só acrescenta o trecho
                por_url[e['url']]['trecho'] = por_url[e['url']].get('trecho') or e.get('trecho', '')
            else:
                rel.append(e)
                por_url[e.get('url')] = e
        py = extracao.extrair(c['cidade'], c['uf'], rel)

    if not rel:
        classif = validacao.classificar(c, [], {'situacao': 'indefinido'}, agora)
        return {'candidato': c, 'evidencias': [], 'descartadas': descartadas, 'fatos': None,
                'classificacao': classif, 'tavily': situacao_tavily, 'llm': 'nao_necessario'}

    data_ref = agora.astimezone(FUSO).date().isoformat()
    fatos_llm, situacao_llm = llm.extrair(c['cidade'], c['uf'], rel, data_ref, cotas, cache)
    fatos = validacao.mesclar(fatos_llm, py)
    fatos, descartes = validacao.ancorar(fatos, rel)
    if fatos.get('situacao') not in ('ocorrencia_confirmada', 'risco_previsto', 'indefinido'):
        fatos['situacao'] = py['situacao']
    classif = validacao.classificar(c, rel, fatos, agora)
    return {'candidato': c, 'evidencias': rel, 'descartadas': descartadas, 'fatos': fatos,
            'fatos_descartados_por_falta_de_ancora': descartes, 'classificacao': classif,
            'tavily': situacao_tavily, 'llm': situacao_llm}


# ------------------------------------------------------------------ execução
def executar(modo: str, agora: datetime | None = None, src=None, saida: Path = Path('output'),
             cache=None, cotas=None, ocorrencias=None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    cfg = config.carregar()
    cache = cache or armazem.Cache()
    cotas = cotas or armazem.Cotas(agora)
    ocorrencias = ocorrencias or armazem.Ocorrencias()
    src = src or FontesAoVivo(cache, agora)
    monitorados = config.municipios_monitorados()

    alertas = src.alertas_defesa_civil() + src.alertas_inmet()
    chuvas, info_chuva, regionais = [], {}, []
    if modo == 'profunda':
        chuvas, info_chuva = src.chuva(monitorados)
        for nome, ch in config.canais_ativos().items():
            uf = ch['uf']
            nome_uf = next((m for m in monitorados if m['uf'] == uf), {}).get('uf')
            estado_nome = {'RJ': 'Rio de Janeiro', 'SP': 'São Paulo', 'RS': 'Rio Grande do Sul', 'PR': 'Paraná',
                           'MG': 'Minas Gerais', 'DF': 'Distrito Federal', 'BA': 'Bahia'}.get(uf, nome_uf)
            if ch.get('recorte'):
                continue        # o recorte é varrido junto com a UF
            for q in fontes.consultas_regionais(estado_nome):
                for n in src.noticias(q):
                    m = municipio_no_titulo(n['titulo'], uf)
                    if m:
                        regionais.append({'ibge': m['codigo_ibge'], 'noticia': n})

    cand = juntar_candidatos(alertas, chuvas, regionais)
    fila = sorted(cand.values(), key=pontuar, reverse=True)
    if modo == 'leve':
        vistos = ocorrencias.d.setdefault('alertas_vistos', {})
        for k in [k for k, quando in vistos.items() if quando < (agora.timestamp() - 3 * 86400)]:
            vistos.pop(k)

        def chave_alerta(c):
            return '|'.join(sorted(f"{c['ibge']}:{a.get('evento')}:{a.get('fim')}" for a in c['alertas']))
        novos_graves = [c for c in fila if any(a.get('severidade') in ('Severe', 'Extreme') for a in c['alertas'])
                        and chave_alerta(c) not in vistos]
        for c in novos_graves:
            vistos[chave_alerta(c)] = agora.timestamp()     # alerta grave novo: investiga UMA vez
        fila = novos_graves
        cotas.prioridade = bool(fila)
    else:
        cotas.prioridade = any(pontuar(c) >= 40 for c in fila)
    limite = cfg['investigacao']['max_aprofundados_por_execucao'] if modo == 'profunda' else 2
    resultados, edicoes = [], []
    for c in fila[:cfg['investigacao']['max_candidatos_por_execucao']]:
        if len(resultados) >= limite and not c['pistas'] and not c['alertas']:
            continue
        if len([r for r in resultados if r['evidencias']]) >= limite:
            break
        r = investigar(c, src, cotas, cache, agora)
        resultados.append(r)
        if not r['fatos']:
            continue
        tipo = roteiro.tipo_principal(r['fatos'])
        oid = armazem.Ocorrencias.id_ocorrencia(c['ibge'], tipo, agora.astimezone(FUSO).date().isoformat())
        r['id'] = oid
        ultima = max((e.get('publicado', '') for e in r['evidencias']), default='') or agora.isoformat()
        anterior = ocorrencias.ativa(oid) or {}
        ocorrencias.atualizar(oid, {'cidade': c['cidade'], 'uf': c['uf'], 'canal': c['canal'], 'tipo': tipo,
                                    'status': r['classificacao']['status'], 'primeira_vez': anterior.get('primeira_vez', agora.isoformat()),
                                    'ultima_evidencia': ultima if 'T' in ultima else agora.isoformat(),
                                    'ultima_execucao': agora.isoformat()})
        fazer, motivo, novos = validacao.decisao_edicao(oid, r['fatos'], r['classificacao'], ocorrencias)
        r['edicao'] = {'gerar': fazer, 'motivo': motivo, 'fatos_novos': sorted(novos)}
        if fazer:
            canal = dict(cfg['canais'][c['canal']], nome=c['canal'])
            rot = roteiro.montar(c, r['fatos'], r['evidencias'], agora, canal)
            arq = saida / 'radar' / oid / 'comunicado.yaml'
            roteiro.gravar(rot, arq)
            r['edicao'].update(arquivo=str(arq), canal=c['canal'], duracao_estimada_s=rot['_radar']['duracao_estimada_s'],
                               publicar=config.modo() == 'publicacao' and r['classificacao']['elegivel_publicacao'])
            ocorrencias.registrar_edicao(oid, novos, str(arq), agora.isoformat())
            edicoes.append(r['edicao'])

    ocorrencias.encerrar_antigas(agora)
    relatorio = {
        'consultado_em': agora.isoformat(), 'modo_execucao': modo, 'modo_publicacao': config.modo(),
        'municipios_monitorados': len(monitorados),
        'canais': sorted(config.canais_ativos()),
        'alertas_oficiais': len(alertas), 'chuva_prevista': {'gatilhos': len(chuvas), **info_chuva},
        'pistas_regionais': len(regionais), 'candidatos': len(cand),
        'investigados': [_resumo(r) for r in resultados], 'edicoes': edicoes,
        'cotas': cotas.resumo(), 'cache_acertos': cache.acertos,
        'erros_de_fonte': getattr(src, 'erros', []),
        'ocorrencias_em_andamento': ocorrencias.d['ativas'],
    }
    saida.mkdir(parents=True, exist_ok=True)
    (saida / 'radar_regional.json').write_text(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (saida / 'radar_resumo.md').write_text(resumo_md(relatorio), encoding='utf-8')
    cache.salvar(); cotas.salvar(); ocorrencias.salvar()
    return relatorio


def _resumo(r):
    c = r['candidato']
    return {'id': r.get('id'), 'cidade': c['cidade'], 'uf': c['uf'], 'canal': c['canal'], 'motivos': c['motivos'][:5],
            'classificacao': r['classificacao'], 'tavily': r['tavily'], 'llm': r['llm'],
            'fatos': r['fatos'], 'descartadas': r['descartadas'],
            'fatos_descartados_por_falta_de_ancora': r.get('fatos_descartados_por_falta_de_ancora', []),
            'evidencias': [{k: e.get(k) for k in ('titulo', 'veiculo', 'dominio', 'publicado', 'url', 'oficial', 'origem')}
                           for e in r['evidencias']],
            'edicao': r.get('edicao')}


def resumo_md(rel: dict) -> str:
    L = [f"## Radar de ocorrências — {rel['consultado_em'][:16]} ({rel['modo_execucao']}, {rel['modo_publicacao']})",
         f"Municípios monitorados: {rel['municipios_monitorados']} · alertas oficiais: {rel['alertas_oficiais']} · "
         f"gatilhos de chuva prevista: {rel['chuva_prevista'].get('gatilhos', 0)} · candidatos: {rel['candidatos']}",
         f"Tavily: {rel['cotas']['tavily']['usado_mes']}/{rel['cotas']['tavily']['teto_mes']} no mês · "
         f"OpenRouter: {rel['cotas']['openrouter']['usado_dia']}/{rel['cotas']['openrouter']['teto_dia']} hoje · "
         f"acertos de cache: {rel['cache_acertos']}", '']
    for i in rel['investigados']:
        cl = i['classificacao']
        L.append(f"- **{i['cidade']}/{i['uf']}** → `{cl['status']}` (prioridade {cl['prioridade']}; "
                 f"oficiais {cl['fontes_oficiais']}, veículos {len(cl['veiculos_independentes'])}) — "
                 f"edição: {(i.get('edicao') or {}).get('motivo', '—')}")
    if rel['erros_de_fonte']:
        L += ['', 'Fontes com falha (não significa ausência de ocorrência):']
        L += [f"- {e['fonte']}: {e['erro']}" for e in rel['erros_de_fonte']]
    return '\n'.join(L) + '\n'
