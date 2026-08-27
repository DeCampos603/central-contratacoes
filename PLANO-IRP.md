# Estudo — aba de IRP (participar antes do pregão)

**O que se quer:** a unidade precisa achar IRPs abertas para manifestar interesse
e entrar como **participante** do futuro registro de preços.

**A conclusão, primeiro:** ao contrário das outras três abas, **não existe fonte
pública de IRP**. Testei os quatro caminhos plausíveis e todos fecharam. Isso
muda o que a aba pode ser — não impede que ela exista, mas impede que ela
funcione como as outras.

---

## 1. Por que isso importa mais do que a aba de Adesão

Participar e pegar carona não são a mesma coisa, e a diferença é grande:

| | **Participante** (via IRP) | **Carona** (adesão à ata pronta) |
|---|---|---|
| Quando decide | Antes do edital | Depois da ata assinada |
| Quantidade | A sua entra no total registrado | Limitada a 50% do registrado |
| Depende de terceiro | Não | Sim — a gerenciadora precisa autorizar |
| Concorre com outros caronas | Não | Sim, pelo saldo do teto |
| Prazo | **Mínimo de 8 dias** de janela | Enquanto a ata durar e houver saldo |

A janela de 8 dias é o ponto: perder a IRP significa esperar o próximo ciclo ou
aceitar a posição pior de carona. Uma aba que só avisa depois não serve — é por
isso que ela vale o trabalho, e por isso o prazo é o dado central da tela.

> Os prazos e limites acima vêm do Decreto 11.462/2023 e do manual de IRP.
> **Confirme o texto vigente** antes de usar como regra de decisão: eu li a
> documentação, não validei artigo por artigo.

---

## 2. O que testei, e o que cada caminho respondeu

### a) Dados abertos do Compras.gov.br — **não tem IRP**

Listei todos os caminhos da especificação (`/v3/api-docs`). São 15 módulos:

```
alice · autenticacao · modulo-arp · modulo-contratacoes · modulo-contratos
modulo-fornecedor · modulo-indicadores · modulo-legado · modulo-material
modulo-ocds · modulo-pesquisa-preco · modulo-pgc · modulo-servico
modulo-uasg · usuarios
```

Nenhum endpoint com "irp", "intencao" ou "participante". A API que alimenta a
aba de Adesão simplesmente não cobre a fase anterior.

### b) API legada — **desligada**

`compras.dados.gov.br` tinha `/licitacoes/v1/irps`. Hoje o host **redireciona**
para `dadosabertos.compras.gov.br`, que não tem essa rota:

```
compras.dados.gov.br/licitacoes/v1/irps.json  →  HTTP 404
```

Existe documentação antiga circulando que ainda cita esse endereço. Ele não
funciona mais.

### c) PNCP — **não publica IRP**

O PNCP publica edital, ata e contrato. `tipos_documento=intencao` devolve
**HTTP 400**. Faz sentido: a IRP é anterior à divulgação da contratação, é um
procedimento entre órgãos, e não um ato publicado ao mercado.

### d) Busca pública do Compras.gov.br — **protegida por captcha**

A tela "Compras eletrônicas" tem exatamente o filtro que pareceria servir
("Etapa: abertas para participação"). Mas capturei a chamada que ela faz:

```
GET /comprasnet-fase-externa/public/v1/compras
    ?captcha=<JWT longo>&tamanhoPagina=10&pagina=0&filtro={...}
```

O parâmetro `captcha` é um token assinado, gerado no navegador. É **proteção
anti-automação deliberada**, e não vou contorná-la — nem manualmente, nem por
automação. Some-se a isso que "abertas para participação" ali significa
participação de **fornecedores** na disputa, não de **órgãos** no registro. Não
era a fonte certa de qualquer forma.

### e) O módulo IRP em si — **autenticado**

Segundo o manual oficial, chega-se por *Acesso aos Sistemas → Governo → CPF e
senha → Intenção de Registro de Preços*. Consultar IRP e Manifestar Interesse
vivem dentro do SIASGNet, atrás de login.

---

## 3. As três formas honestas de fazer a aba

Como não há fonte pública, a aba não pode ser "ao vivo do navegador" como o
Procurador nem "gerada por Action" como a Adesão. Sobram três desenhos:

### Opção A — Local, alimentada pelo robô autenticado *(recomendada)*

O `RoboExtratorPregoes_V2` já resolve a parte difícil: abre o **seu** Chrome via
CDP na porta 9222, reaproveita a sessão logada com certificado, troca de UASG por
`POST /alteraruasgusuario` e lê páginas autenticadas. É a mesma mecânica, apontada
para o módulo de IRP.

O robô grava `site/data/irp.json`; a aba lê esse arquivo. **O JSON não é
commitado nem publicado** — a aba funciona quando você roda o site na sua
máquina, e no site público aparece explicando que depende de execução local.

- **A favor:** automatiza de verdade; usa credencial sua, na sua máquina, sem
  guardar senha em lugar nenhum; nada de dado autenticado vai para a internet.
- **Contra:** só funciona com você rodando; exige mapear as telas do IRP (o robô
  hoje conhece as de ata e item, não as de IRP).

### Opção B — Importar o relatório do IRP

Você exporta do próprio sistema e solta o arquivo na aba, que lê no navegador e
monta a tabela com prazos e alertas.

- **A favor:** trabalho pequeno, zero automação, zero questão de credencial.
- **Contra:** depende de você lembrar de exportar — justamente o que a ferramenta
  deveria evitar.

### Opção C — Publicar os dados de IRP no site público

Tecnicamente é A com o JSON commitado.

**Não recomendo sem uma decisão sua explícita.** São dados extraídos de um sistema
com autenticação; ainda que sejam de interesse público, publicá-los é uma decisão
sua e do seu órgão, não uma consequência técnica. E a partir daí o site passa a
depender de você rodar o robô, ou envelhece em silêncio — que é pior do que não
ter a aba.

**Caminho sugerido:** começar por **A**, com **B** como recurso manual para quando
o robô falhar. Se depois o órgão decidir que a publicação é adequada, C é só
mudar o `.gitignore`.

---

## 4. O que a aba mostra

O prazo é o dado principal — tudo o mais é contexto:

```
IRP 90014/2026 · 160264 - BASE ADM ...          [ faltam 3 dias ]
Objeto: material de expediente
Gerenciadora: 160XXX   ·   Itens: 42
Manifestação até 04/09/2026 17:00
[ Ver itens ]  [ Abrir no Compras.gov.br ]
```

- Ordenação padrão: **quem vence antes, primeiro** — não por valor.
- Faixas visuais: ≤2 dias (vermelho), ≤4 (âmbar), resto neutro.
- Filtro por objeto/CATMAT, para achar o que a unidade realmente usa.
- Cruzamento com a aba Adesão: *"já existe ata vigente deste item?"* — se existe,
  talvez não valha entrar na IRP; se não existe, entrar é a única via boa.

Esse cruzamento é o que justifica a aba morar aqui e não num script à parte: as
duas perguntas são a mesma decisão vista de dois ângulos.

---

## 5. Fases

1. **Mapear as telas do IRP** com o navegador logado: URLs, filtros, formato da
   lista e da tela de itens. Sem isso, qualquer estimativa de esforço é chute.
   *Pronto quando:* houver um HTML salvo de cada tela e os seletores anotados.
2. **Extrator** no molde das fases do robô atual, gravando `irp.json` com
   prazo, gerenciadora, objeto, itens e link. *Pronto quando:* duas execuções
   seguidas derem o mesmo resultado.
3. **Aba** lendo o JSON, com contagem regressiva e as faixas de prazo.
   *Pronto quando:* uma IRP com 3 dias restantes aparecer acima de uma com 7.
4. **Cruzamento com Adesão** por CATMAT.
5. **Alerta** (opcional): reaproveitar o envio de e-mail do
   `Monitor-Contratacoes-Diario` para avisar de IRP a vencer.

---

## 6. Riscos

| Risco | Por quê | O que fazer |
|---|---|---|
| Tela some no ar sem a execução local | Opção A depende da sua máquina | A aba diz a data da última extração e avisa quando está velha |
| Dado envelhecer em silêncio | Pior que não ter a aba | Marcar como desatualizado a partir de 24 h |
| Seletores quebrarem | O robô atual já sofre disso | Mesma estratégia: seletor por rótulo, com fallback |
| Publicar dado autenticado sem querer | O `.gitignore` é a única barreira | `site/data/irp.json` ignorado desde o primeiro commit |
| Perder o prazo mesmo com a aba | 8 dias passam rápido | O alerta da fase 5 é o que fecha o buraco |

---

## 7. Decisões suas

1. **A, B ou C?** Recomendo A, com B de reserva.
2. **Quais UASGs vigiar?** Só a 160329, ou também as coirmãs da 1ª RM?
3. **Vale o alerta por e-mail** (fase 5), ou abrir o site basta?

E uma pergunta anterior a todas: **você consegue ver IRPs de outros órgãos no
sistema, ou só as da sua própria unidade?** Isso decide se a aba é uma agenda das
suas IRPs ou um radar de oportunidades — são ferramentas bem diferentes, e eu não
tenho como descobrir sem o acesso.
