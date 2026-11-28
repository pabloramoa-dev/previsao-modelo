import argparse

from src.previsao import estado
from src.previsao.editorial.formats import TITLES


def test_titles_enxerga_os_formatos_do_estado():
    esperados = set(estado.titulos())
    assert esperados, "o estado precisa declarar formatos"
    assert set(TITLES) == esperados
    assert len(TITLES) == len(esperados)
    for chave in esperados:
        assert chave in TITLES
        assert TITLES[chave] == estado.titulos()[chave]


def test_argparse_aceita_os_formatos_do_estado():
    ap = argparse.ArgumentParser()
    ap.add_argument('--format', choices=TITLES)
    for chave in estado.titulos():
        assert ap.parse_args(['--format', chave]).format == chave
