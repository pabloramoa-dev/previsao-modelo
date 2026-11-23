# Atendimento compartilhado de previsão

Um serviço atende @previsaomg, @previsaopr, @previsaors, @otemposp,
@previsaobsb e @previsaovr. Comentário reconhecido recebe a previsão de
hoje e amanhã no direct, seguida de confirmação no comentário. DMs com texto
recebem a previsão no direct. RJ e Sul Flu têm seus webhooks próprios.

## Configuração no Render

- Build: `pip install -r atendimento-rede/requirements.txt`
- Start: `gunicorn --chdir atendimento-rede --bind 0.0.0.0:$PORT --workers 1 --threads 4 app:app`
- Saúde: `/ping`
- `MET_USER_AGENT`: identificador do serviço e contato do responsável.
- `INSTAGRAM_CONTAS`: objeto JSON secreto. Adicione uma entrada por perfil
  com as chaves `instagram_id`, `access_token`, `app_secret` e `verify_token`.
  Use a chave de assinatura do app Meta vinculado ao perfil. A chave externa
  do objeto é o handle em minúsculas, sem @.
- `META_GRAPH_VERSION`: opcional, padrão `v27.0`.
- `ATENDIMENTO_DB`: opcional, caminho do SQLite para deduplicação. Por padrão
  fica em /tmp. Reinício em serviço sem disco persistente pode perder o
  registro de eventos. A fila de entregas é mantida em memória.

## Autorizar cada conta no app da Meta

1. Em Instagram Login, autorize a conta profissional com
   `instagram_business_basic`, `instagram_business_manage_comments` e
   `instagram_business_manage_messages`. Gere um token com os escopos e
   confira se o ID retornado corresponde à conta que vai responder.
2. Configure `https://<servico>/webhook/<perfil>` como callback do app e use
   o verify token dessa entrada. Se várias contas forem autorizadas no
   mesmo app, configure um único callback usando um dos perfis do app.
   O serviço usa o ID da conta no evento e aceita apenas contas associadas
   à mesma chave de assinatura.
3. Assine `comments` e `messages` no app e na inscrição da conta profissional.
4. Teste com outra conta comentando uma localidade atendida em um Reel recente,
   depois envie a mesma localidade por DM. Confira previsão, origem da resposta
   e confirmação pública. Compare também com um comentário sem localidade.

## Atualizar localidades

`catalogos.json` contém os pontos editoriais dos seis canais. Para atualizar,
baixe os arquivos listados em `gerar_catalogos.py` numa pasta com uma subpasta
por repositório, instale PyYAML e rode:

```sh
python atendimento-rede/gerar_catalogos.py /caminho/fontes > atendimento-rede/catalogos.json
```

As previsões consultam MET Norway Locationforecast com cache de três horas.
A resposta usa horário de Brasília e mostra temperaturas das horas disponíveis.
