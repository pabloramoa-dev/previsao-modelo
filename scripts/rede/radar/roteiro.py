"""Roteiro da edição extraordinária (Bira e Bia) a partir dos FATOS VALIDADOS.

Sai um YAML no formato de comunicados/ (hyperframes/comunicado_dupla.py), que
usa o estúdio, as vozes Kokoro, o lip sync e os cenários originais.
O texto é montado por regras a partir dos fatos ancorados: nenhum número,
bairro ou rio entra se não estiver nas fontes. Alvo: 45 a 75 s.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

from . import config

FUSO = ZoneInfo('America/Sao_Paulo')
PALAVRAS_POR_SEG = 2.55          # ritmo medido nas vozes Kokoro da dupla
ROTULO = {
    'transbordamento': 'RIOS TRANSBORDARAM', 'enchente': 'ENCHENTE', 'alagamento': 'ALAGAMENTOS',
    'enxurrada': 'ENXURRADA', 'deslizamento': 'DESLIZAMENTOS', 'granizo': 'CHUVA DE GRANIZO',
    'vendaval': 'VENDAVAL', 'tornado': 'TORNADO', 'ciclone': 'CICLONE', 'temporal': 'TEMPORAL',
}
ORDEM = ('transbordamento', 'enchente', 'deslizamento', 'enxurrada', 'alagamento', 'granizo',
         'tornado', 'vendaval', 'ciclone', 'temporal')
SEGURANCA = {
    'transbordamento': 'Não atravesse rua alagada nem fique perto da margem dos rios.',
    'enchente': 'Não atravesse rua alagada, a pé ou de carro: a correnteza engana.',
    'alagamento': 'Não atravesse rua alagada, a pé ou de carro: a correnteza engana.',
    'deslizamento': 'Quem mora em encosta deve observar rachaduras, estalos e árvores inclinadas, e sair ao menor sinal.',
    'granizo': 'Durante o granizo, fique em local coberto e longe de janelas.',
    'vendaval': 'Com vento forte, fique longe de árvores, placas e fios caídos.',
}


def _lista(xs, n=3):
    xs = list(xs)[:n]
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' e ' + xs[-1] if xs else ''


def _sem_prefixo_rio(r):
    return re.sub(r'^(Rio|Córrego|Corrego|Ribeirão)\s+', '', r)


def _rios_falados(rios):
    if not rios:
        return ''
    nomes = [_sem_prefixo_rio(r) for r in rios[:2]]
    return f'dos rios {nomes[0]} e {nomes[1]}' if len(nomes) == 2 else f'do Rio {nomes[0]}'


def _vias_faladas(vias):
    pre = {'Rua': 'na', 'Avenida': 'na', 'Estrada': 'na', 'Rodovia': 'na', 'Travessa': 'na', 'Ponte': 'na',
           'Viaduto': 'no'}
    partes = [f"{pre.get(v.split()[0], 'na')} {v}" for v in vias[:2]]
    return ' e '.join(partes)


def _com_artigo(lugar):
    fem = ('Escola', 'Igreja', 'Creche', 'Quadra', 'Associação')
    return ('a ' if lugar.split()[0] in fem else 'o ') + lugar


def _mm_falado(mm):
    v = float(mm)
    return f'{v:g}'.replace('.', ',')


def tipo_principal(fatos):
    tipos = set(fatos.get('tipos') or [])
    if fatos.get('rios_corregos') and ('transbordamento' in tipos or 'enchente' in tipos):
        return 'transbordamento'
    for t in ORDEM:
        if t in tipos:
            return t
    return 'temporal'


def montar(oc: dict, fatos: dict, evidencias: list[dict], agora: datetime, canal: dict) -> dict:
    cidade, tp = oc['cidade'], tipo_principal(fatos)
    bairros, rios = fatos.get('bairros') or [], fatos.get('rios_corregos') or []
    mm, periodo = fatos.get('chuva_mm'), fatos.get('periodo') or ''
    acolhidos, vias = fatos.get('desalojados_ou_acolhidos'), fatos.get('vias_interditadas') or []
    apoio, servicos = fatos.get('pontos_de_apoio') or [], fatos.get('servicos_afetados') or []
    tels = [t for t in fatos.get('telefones') or [] if re.sub(r'\D', '', t) not in ('199', '193')]

    # gancho localizado
    if tp == 'transbordamento' and rios:
        gancho = f'Atenção, {cidade}! A chuva forte fez transbordar {"os rios " + _lista([_sem_prefixo_rio(r) for r in rios], 2) if len(rios) > 1 else "o " + rios[0]}.'
    else:
        gancho = f'Atenção, {cidade}! {ROTULO.get(tp, "Temporal").capitalize()} atinge a cidade.'
        gancho = gancho.replace('Rios transbordaram atinge', 'Rios transbordam em')

    falas = [{'cena': 'abertura', 'fala': gancho}]
    detalhe = ' · '.join(bairros[:3]) or cidade.upper()
    if bairros:
        fala = f'Os bairros mais atingidos foram {_lista(bairros, 3)}'
        fala += f', com a cheia {_rios_falados(rios)}.' if rios else '.'
    else:
        fala = f'Equipes da Defesa Civil atendem ocorrências em vários pontos de {cidade}.'
    falas.append({'cena': 'alerta', 'titulo': ROTULO.get(tp, 'TEMPORAL'), 'detalhe': detalhe, 'fala': fala})

    if mm:
        quando = f' entre a {periodo}' if periodo else ' em poucas horas'
        falas.append({'cena': 'numero', 'numero': f'{_mm_falado(mm)} mm', 'sub': 'DE CHUVA',
                      'local': cidade.upper(),
                      'fala': f'Os pluviômetros marcaram cerca de {_mm_falado(mm)} milímetros{quando}.'})
    if acolhidos:
        f = f'{acolhidos} moradores precisaram ir para pontos de apoio'
        f += f', como {_lista([_com_artigo(a) for a in apoio], 2)}.' if apoio else '.'
        falas.append({'cena': 'frase', 'fala': f})
    if vias:
        falas.append({'cena': 'frase', 'fala': f'Também houve ocorrências {_vias_faladas(vias)}.'})
    if servicos:
        falas.append({'cena': 'frase', 'fala': f'O {servicos[0]} também foi afetado em parte da cidade; acompanhe os avisos oficiais.'})
    falas.append({'cena': 'frase', 'fala': SEGURANCA.get(tp, SEGURANCA['alagamento'])})
    emerg = 'Em emergência, ligue 199 para a Defesa Civil ou 193 para os Bombeiros.'
    if tels:
        emerg = f'Em emergência, ligue 199, ou chame a Defesa Civil no {tels[0]}. Bombeiros: 193.'
    falas.append({'cena': 'frase', 'continua': True, 'fala': emerg})
    falas.append({'cena': 'cta', 'chamada': 'AVISE QUEM MORA LÁ', 'sub': '{arroba} · edição extraordinária',
                  'fala': f'Manda esse vídeo pra quem mora em {cidade} e segue a gente pra receber as atualizações.'})

    # duração: corta frases opcionais se passar de 75 s
    def dur(fs):
        return sum(len(f['fala'].split()) for f in fs) / PALAVRAS_POR_SEG + 1.2 * len(fs)
    alvo_min, alvo_max = config.carregar()['edicao']['duracao_alvo_s']
    while dur(falas) > alvo_max:
        opcionais = [i for i, f in enumerate(falas) if f['cena'] == 'frase' and not f.get('continua')]
        if len(opcionais) <= 1:
            break
        falas.pop(opcionais[0])
    # curto demais: completa com orientações gerais (nenhum fato novo é inventado)
    reforcos = [f'A Defesa Civil de {cidade} segue monitorando a situação; acompanhe só os avisos oficiais.',
                'Evite áreas de risco, como encostas e margens de rios, enquanto a chuva continuar.',
                'Se precisar sair de casa, leve documentos e remédios e avise alguém do seu destino.']
    while dur(falas) < alvo_min and reforcos:
        falas.insert(len(falas) - 2, {'cena': 'frase', 'fala': reforcos.pop(0)})

    fontes_txt = []
    for e in evidencias:
        nome = e.get('veiculo') or e.get('dominio')
        if nome and nome not in fontes_txt:
            fontes_txt.append(nome)
    validade = (agora + timedelta(hours=8)).astimezone(FUSO).strftime('%Y-%m-%dT%H:%M')   # comunicado lê no fuso de Brasília
    ticker = [x for x in [f'{_mm_falado(mm)} MM DE CHUVA' if mm else '',
                          f'RIOS {" E ".join(_sem_prefixo_rio(r).upper() for r in rios[:2])}' if len(rios) > 1 else '',
                          f'{acolhidos} EM PONTOS DE APOIO' if acolhidos else '',
                          'DEFESA CIVIL 199', 'BOMBEIROS 193'] if x]
    legenda = [f'⚠️ {cidade.upper()} — {ROTULO.get(tp, "TEMPORAL")}']
    if mm:
        legenda.append(f'🌧️ Cerca de {_mm_falado(mm)} mm de chuva' + (f' entre a {periodo}' if periodo else ''))
    if rios:
        legenda.append('🌊 ' + _lista(rios, 3))
    if bairros:
        legenda.append('📍 Bairros: ' + _lista(bairros, 6))
    if acolhidos:
        legenda.append(f'🏫 {acolhidos} moradores em pontos de apoio' + (f' ({_lista(apoio, 2)})' if apoio else ''))
    if servicos:
        legenda.append('🚰 Serviço afetado: ' + _lista(servicos, 2))
    legenda.append('📞 Defesa Civil 199 · Bombeiros 193' + (f' · Defesa Civil local {tels[0]}' if tels else ''))
    legenda.append('Manda pra quem mora na região! {arroba}')
    legenda.append(f"#{re.sub(r'[^A-Za-zÀ-ÿ0-9]', '', cidade.title())} #Chuva #DefesaCivil #EdicaoExtraordinaria")
    data = agora.astimezone(FUSO).strftime('%d/%m')
    return {
        'tipo': 'alerta', 'apresenta': config.carregar()['edicao']['apresenta'], 'validade': validade,
        'titulo': f'{cidade.upper()}: {ROTULO.get(tp, "TEMPORAL")}'[:34],
        'etiquetas': ['EXTRAORDINÁRIA', f'{data} · CONFIRMADO'],     # cabem na etiqueta da abertura
        'ceu': 'chuva', 'trilha': False,
        'fonte': '; '.join(fontes_txt[:5]),          # o comunicado acrescenta "Fonte: ..." na legenda
        'ticker': ticker, 'falas': falas, 'legenda': '\n'.join(legenda) + '\n',
        '_radar': {'canal': canal, 'duracao_estimada_s': round(dur(falas), 1)},
    }


def gravar(roteiro: dict, caminho) -> None:
    r = {k: v for k, v in roteiro.items() if not k.startswith('_')}
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text('# Gerado pelo Radar de Ocorrências — conferir antes de publicar.\n'
                       + yaml.safe_dump(r, allow_unicode=True, sort_keys=False, width=110), encoding='utf-8')
