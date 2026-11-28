"""Regra editorial da rede: >= 50 mm em 24 h abre o vídeo com alerta localizado."""
import pytest

from src.previsao.editorial.formats import abertura_chuva_24h


@pytest.mark.parametrize("mm, obrigatorio", [
    (49.9, False), (50, True), (80, True), (100, True), (143.2, True)])
def test_limiar_de_50_mm(mm, obrigatorio):
    bloco = {"locations": [{"name": "Cidade A", "rain_mm": mm}, {"name": "Cidade B", "rain_mm": 3}]}
    for quando in ("hoje", "amanhã"):
        beat = abertura_chuva_24h(bloco, quando)
        if not obrigatorio:
            assert beat is None
            continue
        assert beat is not None
        assert "Se você mora em Cidade A, preste atenção!" in beat["fala"]
        assert "Cidade B" not in beat["fala"]
        assert f"{mm:g}".replace(".", ",") + " milímetros" in beat["fala"]
        assert "defesa civil" not in beat["fala"].lower()


@pytest.mark.parametrize("valor", [None, "muito", float("nan"), float("inf"), True, -5])
def test_dados_ausentes_ou_invalidos_nao_geram_alerta_falso(valor):
    bloco = {"locations": [{"name": "Cidade A", "rain_mm": valor}, {"name": None, "rain_mm": 120},
                           {"name": "Cidade B"}]}
    assert abertura_chuva_24h(bloco, "amanhã") is None
    assert abertura_chuva_24h({}, "hoje") is None
