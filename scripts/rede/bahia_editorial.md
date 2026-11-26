# Cobertura editorial — Previsão Bahia

O perfil @previsaobahia tem nove macroáreas editoriais (não são uma divisão administrativa oficial), 54 municípios de referência com coordenadas do cadastro IBGE e representação dos 27 Territórios de Identidade. O cadastro original contém os 417 municípios, mas a previsão diária por ponto não equivale a uma previsão individual para todos eles. Os dois boletins recolhem todos os 54 pontos (tier 2), e alternam os nomes das cidades na tela por dia e turno; uma ausência de dados nunca deve ser preenchida com valores de outra cidade. O quadro de nove linhas exige aprovação visual no piloto antes de ativar publicações.

| Macroárea | Territórios | Municípios de referência | Foco editorial |
|---|---|---|---|
| Litoral Norte e Salvador | Metropolitano de Salvador; Litoral Norte e Agreste Baiano | Salvador, Camaçari, Lauro de Freitas, Mata de São João, Alagoinhas, Conde | Brisa marítima, chuva costeira, alagamentos urbanos e turismo. |
| Feira e Recôncavo | Portal do Sertão; Recôncavo; Bacia do Jacuípe; Piemonte do Paraguaçu | Feira de Santana, Santo Antônio de Jesus, Cruz das Almas, Ipirá, Itaberaba, Cachoeira | Transição litoral-interior, calor, pancadas, travessias e rios. |
| Nordeste e Sisal | Sisal; Semiárido Nordeste II; Itaparica | Serrinha, Conceição do Coité, Euclides da Cunha, Ribeira do Pombal, Paulo Afonso | Calor, baixa umidade, estiagem, chuvas concentradas e vento. |
| Norte e São Francisco | Sertão do São Francisco; Piemonte Norte do Itapicuru; Piemonte da Diamantina | Juazeiro, Casa Nova, Remanso, Senhor do Bonfim, Jacobina | Calor, umidade, agricultura irrigada, rios e reservatórios. |
| Chapada e Centro | Chapada Diamantina; Irecê; Bacia do Paramirim | Lençóis, Seabra, Irecê, Macaúbas, Morro do Chapéu, Mucugê, Piatã | Altitude, amplitude térmica, nevoeiro, chuva localizada e risco em cachoeiras. |
| Oeste e Velho Chico | Bacia do Rio Grande; Bacia do Rio Corrente; Velho Chico | Barreiras, Luís Eduardo Magalhães, Formosa do Rio Preto, Santa Maria da Vitória, Bom Jesus da Lapa, Ibotirama, Correntina | Chuvas de verão, raios, granizo, estiagem, queimadas e agricultura. |
| Sudoeste e Vales | Sudoeste Baiano; Sertão Produtivo; Médio Sudoeste da Bahia; Médio Rio de Contas; Vale do Jiquiriçá | Vitória da Conquista, Guanambi, Itapetinga, Jequié, Amargosa, Brumado | Altitude, noites frias, nevoeiro, contrastes térmicos e chuva intensa. |
| Litoral Sul e Baixo Sul | Litoral Sul; Baixo Sul | Ilhéus, Itabuna, Itacaré, Valença, Camamu, Cairu | Umidade elevada, chuva costeira, rios, cacau, praias e travessias. |
| Litoral do Extremo Sul | Costa do Descobrimento; Extremo Sul | Porto Seguro, Eunápolis, Teixeira de Freitas, Caravelas, Mucuri, Prado | Frentes frias, chuva intensa, enchentes, turismo e condições costeiras. |

## Clima e serviço público

- No litoral leste, o outono e o início do inverno costumam ter maiores volumes de chuva; no Centro-Sul e Oeste, o período chuvoso normalmente ganha força na primavera. Não aplicar calendário sazonal como previsão de um dia específico.
- Chapada e planaltos: considerar diferenças de altitude e evitar extrapolar a sede municipal para trilhas ou cachoeiras. Em caso de chuva intensa a montante, orientar seguir avisos locais.
- Semiárido, São Francisco e Cerrado: priorizar calor, baixa umidade, seca e queimadas; durante episódios de chuva, raios e alagamentos repentinos.
- Litoral: distinguir previsão atmosférica, balneabilidade, maré, ondas e ressaca. Não afirmar segurança para banho sem fonte adequada.
- Maior chuva prevista: destacar a cidade, período e acumulado, informando que é previsão, e jamais inventar rajadas, probabilidade de chuva ou UV se o provedor não entregar esses campos.
- Alertas oficiais: monitorar vigência, municípios afetados, autoridade emissora e deduplicar. O monitor estadual e o envio automático de alertas ainda precisam ser implementados/testados; este documento é requisito editorial, não confirmação de integração. O monitor nacional permanece no repositório-modelo.

## Fontes oficiais para integração e checagem

- [Inema: previsão do tempo](https://www.ba.gov.br/inema/servicos/tempo-e-clima/previsao-do-tempo) — oito mesorregiões meteorológicas oficiais.
- [Inema: boletim operacional](https://www.ba.gov.br/inema/iniciativas/previsao-do-tempo).
- [Inema: ferramentas de meteorologia](https://www.ba.gov.br/inema/paginas) — painéis com dados dos 417 municípios.
- [SUDEC: avisos e alertas](https://www.ba.gov.br/defesacivil/servicos/avisos-e-alertas).
- [INMET: avisos](https://alertas2.inmet.gov.br/).
- [Marinha: avisos de mau tempo](https://www.marinha.mil.br/chm/dados-do-smm-avisos-de-mau-tempo/avisos-de-mau-tempo).
- [Divisão territorial oficial da Bahia](https://www.ba.gov.br/cultura/314/divisao-territorial-da-bahia).

## Entrada em operação

Alvo: 06:00 e 18:00 BRT, sem publicação até configurar credenciais exclusivas do perfil e AUTOMATION_ENABLED=true. Usar MET Norway conforme licenciamento e configuração original. Verificar CI, coleta completa, rodízio, renderização das nove linhas, legibilidade, duração e ausência de duplicação antes de conectar a Meta. O alerta não deve ser publicado até a integração regional ser validada.
