"""Radar de ocorrências: regras, segurança e o caso histórico de Barra Mansa (offline)."""
from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REDE = Path(__file__).resolve().parents[1] / 'scripts' / 'rede'
sys.path.insert(0, str(REDE))
CASO = Path(__file__).resolve().parent / 'fixtures' / 'radar' / 'barra_mansa_2026-11-26.json'


@pytest.fixture()
def estado_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv('RADAR_ESTADO', str(tmp_path / 'estado'))
    return tmp_path


def test_self_test(estado_tmp):
    rr = importlib.import_module('radar_regional')
    rr.self_test()


def test_caso_barra_mansa_e_duplicidade(estado_tmp, monkeypatch):
    from radar import caso_teste
    rel, esperado, src = caso_teste.rodar(str(CASO), estado_tmp / 'out')
    assert caso_teste.conferir(rel, esperado) == []
    assert len(rel['edicoes']) == 1
    assert rel['modo_publicacao'] == 'simulacao' and not rel['edicoes'][0]['publicar']
    assert rel['cotas']['tavily']['nesta_execucao'] == 1
    yaml_txt = Path(rel['edicoes'][0]['arquivo']).read_text(encoding='utf-8')
    assert 'Nova Esperança' in yaml_txt and 'Bananal' in yaml_txt
    assert 'api_key' not in yaml_txt.casefold() and 'ignore' not in yaml_txt.casefold()
    assert '87' not in yaml_txt          # chuva de Resende não pode virar a de Barra Mansa
    oid = rel['edicoes'][0]['id']
    # enquanto o vídeo não fica pronto: não repete a edição
    rel2, _, src2 = caso_teste.rodar(str(CASO), estado_tmp / 'out2')
    assert rel2['edicoes'] == [] and 'em produção' in rel2['investigados'][0]['edicao']['motivo']
    assert src2.consultas_tavily == 0                      # cache: sem gastar Tavily de novo
    # vídeo renderizado (artifact edicao-ok-<id>): passa a contar; sem fato novo -> duplicada
    monkeypatch.setenv('RADAR_EDICOES_OK', oid)
    rel3, _, _ = caso_teste.rodar(str(CASO), estado_tmp / 'out3')
    assert rel3['pendencias_resolvidas']['confirmadas'] == [oid]
    assert rel3['edicoes'] == [] and 'duplicada' in rel3['investigados'][0]['edicao']['motivo']


def test_render_que_falhou_nao_trava_a_ocorrencia(estado_tmp):
    from radar import armazem
    agora = datetime.fromisoformat('2026-11-26T14:00:00-03:00')
    oc = armazem.Ocorrencias()
    oc.registrar_pendente('x-enchente-2026-11-26', {'tipo:enchente'}, 'a.yaml', agora.isoformat())
    assert oc.em_producao('x-enchente-2026-11-26')
    res = oc.resolver_pendentes(agora + timedelta(hours=4), set())
    assert res['vencidas'] == ['x-enchente-2026-11-26'] and not oc.em_producao('x-enchente-2026-11-26')
    assert not oc.fatos_ja_publicados('x-enchente-2026-11-26')      # pode gerar de novo


def test_noticia_antiga_e_fora_do_municipio(estado_tmp):
    from radar import validacao
    agora = datetime.fromisoformat('2026-11-26T14:00:00-03:00')
    velha = {'titulo': 'Enchente em Barra Mansa', 'publicado': '2026-02-10T10:00:00-03:00', 'url': 'https://x.com.br/a'}
    assert validacao.evidencia_relevante(velha, 'Barra Mansa', agora, 36) == (False, 'antiga')
    outra = {'titulo': 'Enchente em Resende', 'publicado': '2026-11-26T10:00:00-03:00', 'url': 'https://x.com.br/b'}
    assert validacao.evidencia_relevante(outra, 'Barra Mansa', agora, 36)[1] == 'nao_cita_municipio'


def test_fato_sem_ancora_e_descartado(estado_tmp):
    from radar import validacao
    ev = [{'titulo': 'Rio Bananal transborda em Barra Mansa', 'trecho': 'bairro Boa Sorte alagado; 70 mm'}]
    fatos = {'bairros': ['Boa Sorte', 'Bairro Inventado'], 'rios_corregos': ['Rio Bananal'], 'chuva_mm': 300,
             'telefones': ['199', '(24) 90000-0000']}
    limpo, desc = validacao.ancorar(fatos, ev)
    assert limpo['bairros'] == ['Boa Sorte'] and limpo['chuva_mm'] is None and limpo['telefones'] == ['199']
    assert 'bairros:Bairro Inventado' in desc


def test_contradicao_de_vitimas_bloqueia(estado_tmp):
    from radar import validacao
    agora = datetime.fromisoformat('2026-11-26T14:00:00-03:00')
    ev = [{'titulo': 'a', 'dominio': 'a.com.br'}, {'titulo': 'b', 'dominio': 'b.com.br'}]
    fatos = {'situacao': 'ocorrencia_confirmada', 'mortes': 2, '_python': {'mortes': 1}, 'contradicoes': []}
    c = validacao.classificar({'alertas': []}, ev, fatos, agora)
    assert c['status'] == 'bloqueada_contradicao' and not c['elegivel_publicacao']


def test_so_modelos_gratuitos(estado_tmp):
    from radar import llm
    with pytest.raises(AssertionError):
        llm.chamar('openai/gpt-4o', [])


def test_modo_variavel_so_restringe(monkeypatch):
    from radar import config
    monkeypatch.setenv('RADAR_MODO', 'publicacao')
    assert config.modo() == config.carregar()['modo']      # env não libera publicação
    monkeypatch.setenv('RADAR_MODO', 'simulacao')
    assert config.modo() == 'simulacao'
