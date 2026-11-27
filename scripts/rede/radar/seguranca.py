"""Texto de fora (notícias, páginas, respostas de API) é DADO, nunca instrução.

- limpa caracteres de controle, marcação e trechos tipo "ignore as instruções"
- corta tamanho
- o que o LLM devolve só é aceito se cada fato estiver ancorado nas fontes
- URLs e telefones da saída só valem se vieram da entrada (ou forem oficiais)
- nenhuma resposta externa vira comando, caminho de arquivo ou variável
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import config

_CTRL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]')
_TAGS = re.compile(r'<[^>]{0,400}>')
_INJ = re.compile(
    r'(ignore|desconsidere|esque[cç]a)\s+(todas?\s+)?(as\s+)?(instru[cç][oõ]es|regras|anteriores|previous|instructions)'
    r'|system\s*prompt|you\s+are\s+now|voc[eê]\s+agora\s+[eé]|<\s*/?\s*(system|assistant|user)\s*>'
    r'|api[_\s-]?key|token|secret|senha|password|curl\s+|wget\s+|rm\s+-rf|\$\(|`',
    re.I)


def limpar(texto, limite: int = 1200) -> str:
    t = _TAGS.sub(' ', str(texto or ''))
    t = _CTRL.sub('', t)
    t = _INJ.sub('[removido]', t)
    t = ' '.join(t.split())
    return t[:limite]


def dominio(url: str) -> str:
    try:
        h = (urlparse(url).hostname or '').casefold()
    except ValueError:
        return ''
    return h[4:] if h.startswith('www.') else h


def eh_oficial(url_ou_dominio: str) -> bool:
    d = dominio(url_ou_dominio) if '://' in str(url_ou_dominio) else str(url_ou_dominio).casefold()
    return any(m in d for m in config.carregar()['editorial']['dominios_oficiais'])


def url_segura(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme == 'https' and bool(u.hostname) and len(url) < 600


def telefones_validos(tels, fontes_texto: str) -> list[str]:
    """Telefone só entra se for oficial nacional ou aparecer literalmente nas fontes."""
    oficiais = set(config.carregar()['editorial']['telefones_oficiais'])
    so_digitos = re.sub(r'\D', '', fontes_texto)
    ok = []
    for t in tels or []:
        d = re.sub(r'\D', '', str(t))
        if not d:
            continue
        if d in oficiais or (len(d) >= 8 and d in so_digitos):
            ok.append(str(t).strip()[:30])
    return list(dict.fromkeys(ok))


def ancorado(termo: str, fontes_texto_norm: str) -> bool:
    """Bairro, rio, rua: só aceita se o nome aparece nas fontes (anti-alucinação)."""
    n = config.norm(termo).strip()
    return len(n) >= 3 and n in fontes_texto_norm
