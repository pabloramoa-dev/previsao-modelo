# Rede de canais estaduais

- `estados.yaml` — os 24 estados: nome, artigo, título, grupo de horário, cenário e as
  seis regiões do quadro (âncora + reservas). É o único arquivo a editar para mudar
  cidades ou regiões de um estado.
- `municipios.csv`, `ufs.csv` — cadastro de municípios do IBGE com coordenadas e fuso,
  de [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros)
  (licença MIT, Copyright (c) 2016 Kelvin S. do Prado).

Gerar um estado: `python -m scripts.novo_estado PR --destino ../previsao-pr`.

## Radar de Ocorrências Meteorológicas Regionais

Central (roda **só aqui**, no modelo) e atende toda a rede: uma pesquisa por
ocorrência serve a todos os canais. Configuração única: `radar.yml`.

- **O que monitora:** todos os municípios das UFs com canal ativo (≈2.500),
  independente do rodízio das previsões diárias. Sul Fluminense tem recorte
  próprio (`recortes.sulflu`). UF nova = acrescentar o canal em `radar.yml`.
- **Fontes grátis:** Defesa Civil/IDAP (CAP), INMET (avisos), Google Notícias
  RSS (imprensa regional, prefeituras, órgãos estaduais) e chuva prevista da
  MET Norway (a fonte da rede; vira "risco previsto", nunca "ocorrência").
- **Créditos:** Tavily só para aprofundar uma ocorrência já detectada;
  OpenRouter só com modelos `:free` (trava no código + chave com limite de
  US$ 1 e conta sem créditos). Tetos e contadores em `radar.yml -> cotas` e
  no estado `cotas.json`; cache de consultas evita pesquisa repetida. Sem
  crédito, a extração em Python (`radar/extracao.py`) assume. Custo: R$ 0.
- **Gatilhos internos** (não são classificação oficial): 20 mm/1h, 40 mm/3h,
  50 mm/24h, 80 mm/48h, 120 mm/72h; prioridade máxima acima de 100 mm/24h,
  alerta oficial grave ou ocorrência confirmada. Ajuste por UF/canal em
  `limiares.ajustes`.
- **Segurança editorial:** evidência precisa citar o município e ser recente;
  notícia antiga é descartada; bairro/rio/rua/número só entra se estiver
  escrito nas fontes; "confirmada" exige fato ocorrido + 1 fonte oficial ou
  2 veículos independentes; contradição sobre vítimas/datas bloqueia; texto
  externo é tratado como dado (nada vira comando, e as chaves nunca vão ao LLM).
- **Edição extraordinária:** roteiro em YAML para `hyperframes/comunicado_dupla.py`
  (Bira e Bia, vozes Kokoro, estúdio HyperFrames, 1080×1920, alvo 45–75 s,
  gancho com o nome da cidade e CTA de compartilhamento). Identidade do canal:
  `config/` do repositório do canal ou `identidades/<canal>/estado.yaml`.
- **Duplicidade:** cada ocorrência tem id (município + tipo + dia); nova
  edição só com fatos novos relevantes.
- **Modo:** `modo: simulacao` (padrão) gera relatório, roteiro e MP4 como
  artifact e não publica. Publicação automática só depois da aprovação.

Teste offline do caso histórico (Barra Mansa, 26/11/2026):

    python scripts/rede/radar_regional.py --caso tests/fixtures/radar/barra_mansa_2026-11-26.json --saida output/caso_teste
