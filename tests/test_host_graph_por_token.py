from src.previsao.publish import instagram


def test_token_login_instagram_usa_graph_instagram(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "IGAAexemplo")
    assert instagram.base_url("v26.0") == "https://graph.instagram.com/v26.0"


def test_token_usuario_do_sistema_usa_graph_facebook(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "EAAexemplo")
    assert instagram.base_url("v26.0") == "https://graph.facebook.com/v26.0"


def test_sem_token_usa_graph_facebook(monkeypatch):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    assert instagram.base_url("v26.0").startswith("https://graph.facebook.com/")
