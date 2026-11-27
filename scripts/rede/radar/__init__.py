"""Radar de Ocorrências Meteorológicas Regionais (rede de previsão).

Módulos:
  config      leitura de scripts/rede/radar.yml e roteamento município -> canal
  armazem     estado persistente: cache de consultas, cotas, ocorrências
  seguranca   higiene de texto externo (anti prompt-injection) e checagens
  fontes      IDAP/Defesa Civil (CAP), INMET, Google Notícias RSS, MET Norway
  tavily      pesquisa aprofundada (franquia gratuita, com teto)
  llm         OpenRouter só com modelos :free, saída JSON validada
  extracao    alternativa 100% Python (sem crédito nenhum)
  validacao   confirmação, frescor, contradições, deduplicação
  roteiro     comunicado em dupla (Bira e Bia) para hyperframes/comunicado_dupla.py
  motor       orquestra uma execução (leve ou profunda)

Nada aqui publica. A publicação continua nos workflows de cada canal e só
acontece com modo=publicacao e a ocorrência elegível.
"""
