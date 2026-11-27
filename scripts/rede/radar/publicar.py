"""Publica no Instagram de UM canal a edição extraordinária feita pelo radar.

Roda no repositório do canal (workflow publicar_radar.yml), com os secrets do
próprio canal (IG_USER_ID, IG_ACCESS_TOKEN). O vídeo vem de um Release
público do previsao-modelo; nenhum outro endereço é aceito.

Travas:
- a conta do token tem de ser exatamente o @ do canal pedido;
- sem --publicar é só conferência (dry-run): nada é criado na Meta;
- se um post recente do perfil já tem o mesmo título, não publica de novo.

    python publicar.py --video-url URL --legenda LEGENDA.txt --handle previsaosulflu [--capa-url URL] [--publicar]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ORIGEM = '/pabloramoa-dev/previsao-modelo/releases/download/'


def _req(url: str, dados: dict | None = None) -> dict:
    corpo = urlencode(dados).encode() if dados is not None else None
    try:
        with urlopen(Request(url, data=corpo, method='POST' if corpo else 'GET'), timeout=60) as r:
            return json.loads(r.read() or b'{}')
    except HTTPError as e:   # mostra o erro da Meta sem o token (vai no corpo, não na URL de erro)
        raise RuntimeError(f'Meta HTTP {e.code}: {e.read().decode("utf-8", "replace")[:600]}') from None


def url_permitida(url: str) -> bool:
    u = urlparse(url)
    return (u.scheme == 'https' and u.netloc == 'github.com' and u.path.startswith(ORIGEM)
            and not u.query and not u.fragment)


def titulo(legenda: str) -> str:
    return next((l.strip() for l in legenda.splitlines() if l.strip()), '')[:120]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video-url', required=True)
    ap.add_argument('--legenda', required=True)
    ap.add_argument('--handle', required=True)
    ap.add_argument('--capa-url', default='')
    ap.add_argument('--publicar', action='store_true')
    a = ap.parse_args()

    if not url_permitida(a.video_url) or (a.capa_url and not url_permitida(a.capa_url)):
        sys.exit('BLOQUEADO: vídeo/capa só de Release público do previsao-modelo')
    legenda = open(a.legenda, encoding='utf-8').read().strip()[:2200]
    handle = a.handle.lstrip('@').casefold()
    if f'@{handle}' not in legenda.casefold():
        sys.exit(f'BLOQUEADO: a legenda não marca @{handle}')

    user = os.environ.get('IG_USER_ID', '').strip()
    token = os.environ.get('IG_ACCESS_TOKEN', '').strip()
    if not user or not token:
        sys.exit('IG_USER_ID/IG_ACCESS_TOKEN ausentes')
    host = 'graph.facebook.com' if token.startswith('EAA') else 'graph.instagram.com'
    base = f"https://{host}/{os.environ.get('META_GRAPH_VERSION') or 'v26.0'}"

    conta = _req(f'{base}/{user}?' + urlencode({'fields': 'id,username', 'access_token': token}))
    if (conta.get('username') or '').casefold() != handle:
        sys.exit(f"BLOQUEADO: token é de @{conta.get('username')}, pedido @{handle}")
    print('destino conferido: @' + handle)

    recentes = _req(f'{base}/{user}/media?' + urlencode({'fields': 'caption', 'limit': 25, 'access_token': token}))
    if any(titulo(m.get('caption') or '') == titulo(legenda) for m in recentes.get('data', [])):
        sys.exit('DUPLICADA: já existe post recente com este título; nada publicado')

    print('legenda:\n' + legenda)
    if not a.publicar:
        print('CONFERÊNCIA (dry-run): nada foi publicado')
        return

    dados = {'media_type': 'REELS', 'video_url': a.video_url, 'caption': legenda,
             'share_to_feed': 'true', 'access_token': token}
    if a.capa_url:
        dados['cover_url'] = a.capa_url
    cid = _req(f'{base}/{user}/media', dados)['id']
    for _ in range(60):
        time.sleep(10)
        st = _req(f'{base}/{cid}?' + urlencode({'fields': 'status_code', 'access_token': token})).get('status_code')
        if st == 'FINISHED':
            break
        if st == 'ERROR':
            sys.exit('Meta recusou o vídeo (status ERROR)')
    else:
        sys.exit('vídeo não ficou pronto na Meta em 10 min')
    mid = _req(f'{base}/{user}/media_publish', {'creation_id': cid, 'access_token': token})['id']
    print('PUBLICADO media_id=' + mid)


if __name__ == '__main__':
    main()
