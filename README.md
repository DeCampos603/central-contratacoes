# Central de Contratações

Três ferramentas de compras públicas em um site só, por abas:

| Aba | O que responde | Como funciona |
|---|---|---|
| **Procurador** | O que está sendo licitado agora? | Busca **ao vivo** no PNCP, do navegador |
| **Adesão** | Dá para pegar carona em ata de outro órgão? | Dados gerados por Action diária |
| **Raio-X** | Com quem eu estaria lidando? | Consulta **ao vivo** à API no Render |

O ganho não é ter as três no mesmo endereço — é o **CNPJ como chave de junção**.
Cada item de ata traz o CNPJ do fornecedor, então a tabela da Adesão tem um botão
**"Raio-X deste fornecedor"** que já leva o CNPJ para a outra aba.

Foi assim que o primeiro teste encontrou um fornecedor com **sanção ativa no CEIS**
numa ata vigente aberta a adesão.

## Por que só uma aba tem dados pré-gerados

Duas das três APIs deixam o navegador chamá-las direto:

| API | `Access-Control-Allow-Origin` | Consequência |
|---|---|---|
| PNCP (`/api/search/`) | `*` | Aba Procurador é 100% cliente |
| Raio-X (Render) | ecoa a origem | Aba Raio-X é 100% cliente |
| Compras.gov.br (dados abertos) | **ausente** | Aba Adesão **precisa** ser pré-gerada |

A resposta do Compras.gov.br chega com HTTP 200 e `Vary: Origin`, mas sem o
cabeçalho — o navegador bloqueia a leitura. É a única razão pela qual existe uma
Action neste projeto.

## Configuração

Tudo o que precisa ser configurado está em [`site/assets/config.js`](site/assets/config.js):

```js
RAIOX_API: "https://raiox-fornecedor-api.onrender.com",
```

Nenhuma credencial mora aqui. As chaves do Raio-X (Portal da Transparência,
DataJud, SERPRO) existem **só** como variáveis de ambiente no Render.

## Rodar local

```bash
pip install -r requirements.txt && python gerar_site.py --pdm 14936 --pdm 309 --saldo 400
```

```bash
python -m http.server 8160 --directory site
```

Para a varredura nacional completa: `python gerar_site.py --meses 24 --saldo 5000`.

## Publicar

O workflow [`publicar-site.yml`](.github/workflows/publicar-site.yml) roda todo dia
às 06h40 (BRT): gera os dados da Adesão e publica via **Pages → Source: GitHub
Actions**. Os dados vão como artefato, sem serem commitados.

## Números medidos

Contra os serviços reais, em 26–27/08/2026 — não são estimativas:

| Medição | Valor |
|---|---|
| Varredura nacional da ARP, 24 meses | ~2.540 páginas × 1,3 s ≈ 55 min |
| Verificação de saldo, 6 threads | 0,57 s/item (393 de 400 no teste) |
| Render acordar | ~22 s |
| Dossiê completo do Raio-X | **~77 s** (as fontes são consultadas em sequência) |
| Busca no PNCP | segundos |

Os 77 s do Raio-X são o motivo do cronômetro na tela: sem ele, a pessoa acha que
travou. E o Render hiberna quando fica ocioso, somando os ~22 s na primeira
consulta do dia.

## As três armadilhas que o código trata

Todas descobertas testando contra os serviços, não supostas.

1. **O PNCP derruba conexões em rajada.** Requisições seguidas voltaram vazias.
   Daí o atraso ao digitar e a repetição — e, sobretudo, a regra de **nunca
   mostrar "nenhum resultado" quando a consulta falhou**.
2. **`tipos_documento` é obrigatório na busca do PNCP.** Sem ele a resposta vem
   **vazia com HTTP 200** — falha silenciosa que pareceria ausência de resultado.
3. **Limite de adesão zero significa "vedado", não "esgotado".** Boa parte das
   atas não admite carona; esses itens ficam ocultos por padrão e aparecem
   marcados como *não permite*, nunca como "0".

As três são a mesma ideia, que o Raio-X já defendia: **"consultei e nada consta"
não é "não consegui consultar"**. Um sistema que confunde as duas mente
exatamente quando mais importa.

## Estrutura

```
site/index.html            casca e as três abas
site/assets/config.js      único ponto de configuração
site/assets/comum.{css,js} tokens, tema, formatação pt-BR, fetch com repetição
site/assets/procurador.js  busca ao vivo no PNCP
site/assets/adesao.js      dados pré-gerados + ponte para o Raio-X
site/assets/raiox.js       consulta ao vivo, cinco estados de fonte
adesao/                    cliente Python da API de dados abertos
gerar_site.py              gera site/data (índice + uma fatia por PDM)
```

## Projetos relacionados

- [`adesao-arp`](https://github.com/DeCampos603/adesao-arp) — a Adesão como
  ferramenta isolada, com CLI e planilha `.xlsx`
- `raiox-fornecedor-api` — a API que a aba Raio-X consulta
- `Monitor-Contratacoes-Diario` — alerta diário por e-mail de licitações de saúde
  no RJ; segue separado, com escopo próprio
