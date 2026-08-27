# -*- coding: utf-8 -*-
"""Pipeline de busca de itens de ARP disponiveis para adesao (carona).

Fluxo:

  1. `2_consultarARPItem` filtrado por CATMAT / PDM / UASG / fornecedor dentro de
     uma janela de vigencia INICIAL (a API nao aceita filtro por vigencia final).
  2. Corte local: ata/item nao excluidos, vigencia final ainda com folga, e
     casamento opcional de texto na descricao.
  3. Enriquecimento com `3_consultarUnidadesItem`, que devolve os campos que a
     tela "Solicitar adesao" usa: `aceitaAdesao`, `qtdLimiteAdesao` e
     `saldoAdesoes` (o quanto AINDA cabe de adesao). Esse passo e caro -- roda
     so sobre os candidatos ja filtrados.

Verificado contra a ata 04002/2024 (UASG 160345), item 00003:
  quantidadeRegistrada 75.000 -> qtdLimiteAdesao 150.000, saldoAdesoes 150.000,
  aceitaAdesao true.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from .api import Cliente

# A API so casa numeroItem no formato zero-padded de 5 digitos: "00002" funciona,
# "2" devolve lista vazia sem erro. Custou uma consulta em branco para descobrir.
LARGURA_NUMERO_ITEM = 5


def normalizar(texto: str) -> str:
    """Minusculas, sem acento -- para casar texto digitado com a descricao."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def casa_texto(descricao: str, termos: list[str]) -> bool:
    """Todos os termos precisam aparecer na descricao (E logico, sem acento)."""
    if not termos:
        return True
    alvo = normalizar(descricao)
    return all(normalizar(t) in alvo for t in termos)


def _num(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _data(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def coletar_candidatos(cli: Cliente, *, meses: int = 24, catmats: list[int] | None = None,
                       pdms: list[int] | None = None, uasgs: list[str] | None = None,
                       fornecedor: str | None = None, modalidade: str | None = None,
                       termos: list[str] | None = None, dias_min: int = 30,
                       hoje: date | None = None, log=print) -> list[dict]:
    """Passos 1 e 2: busca bruta na API e corte local. Nao consulta o endpoint 3."""
    hoje = hoje or date.today()
    inicio = (hoje - timedelta(days=int(meses * 30.5))).isoformat()
    fim = hoje.isoformat()
    corte_vigencia = hoje + timedelta(days=dias_min)

    # Cada filtro de codigo vira uma consulta propria; a API aceita um valor por vez.
    consultas: list[dict] = []
    for c in (catmats or []):
        consultas.append({"codigoItem": int(c)})
    for p in (pdms or []):
        consultas.append({"codigoPdm": int(p)})
    for u in (uasgs or []):
        consultas.append({"codigoUnidadeGerenciadora": int(u)})
    if fornecedor:
        consultas.append({"niFornecedor": re.sub(r"\D", "", fornecedor)})
    if not consultas:
        consultas.append({})  # varredura ampla: so a janela de datas
    if modalidade:
        for c in consultas:
            c["codigoModalidadeCompra"] = str(modalidade)

    brutos: list[dict] = []
    for filtros in consultas:
        rotulo = ", ".join(f"{k}={v}" for k, v in filtros.items()) or "sem filtro"
        log(f"[1/3] Consultando itens de ARP ({rotulo})...")
        brutos.extend(cli.itens_arp(inicio, fim, **filtros))

    log(f"[2/3] {len(brutos)} itens brutos; aplicando cortes locais...")
    vistos: set[tuple] = set()
    candidatos: list[dict] = []
    for it in brutos:
        if it.get("itemExcluido"):
            continue
        fim_vig = _data(it.get("dataVigenciaFinal"))
        if not fim_vig or fim_vig < corte_vigencia:
            continue
        if not casa_texto(it.get("descricaoItem") or "", termos or []):
            continue
        chave = (it.get("numeroControlePncpAta"), it.get("numeroItem"),
                 it.get("niFornecedor"))
        if chave in vistos:
            continue
        vistos.add(chave)
        it["_diasRestantes"] = (fim_vig - hoje).days
        candidatos.append(it)

    # Ordena JA AQUI, por preco unitario: o enriquecimento (passo 3) e caro e tem
    # orcamento limitado, entao ele precisa ser gasto nos itens mais vantajosos --
    # nao nos primeiros que a API devolveu.
    candidatos.sort(key=lambda it: (_num(it.get("valorUnitario")) or 9e18,
                                    -(it.get("_diasRestantes") or 0)))
    log(f"      {len(candidatos)} candidatos vigentes por >= {dias_min} dias.")
    return candidatos


def enriquecer_com_saldo(cli: Cliente, candidatos: list[dict], *, limite: int = 40,
                         log=print) -> list[dict]:
    """Passo 3: consulta `3_consultarUnidadesItem` por candidato.

    Anota `saldoAdesoes`, `qtdLimiteAdesao` e `aceitaAdesao`. E o passo lento --
    o endpoint chega a levar minutos por chamada, por isso o `limite`.
    Candidatos alem do limite ficam com `_saldoConsultado = False`.
    """
    alvos = candidatos[:limite]
    if len(candidatos) > limite:
        log(f"[3/3] Consultando saldo de adesao dos {limite} primeiros "
            f"(de {len(candidatos)}); use --limite para ampliar.")
    else:
        log(f"[3/3] Consultando saldo de adesao de {len(alvos)} itens (endpoint lento)...")

    for i, it in enumerate(alvos, 1):
        numero_item = str(it.get("numeroItem") or "").zfill(LARGURA_NUMERO_ITEM)
        try:
            unidades = cli.unidades_item(
                it.get("numeroAtaRegistroPreco"),
                it.get("codigoUnidadeGerenciadora"),
                numero_item)
        except Exception as e:
            log(f"      [{i}/{len(alvos)}] falhou: {e}")
            it["_saldoConsultado"] = False
            continue

        it["_saldoConsultado"] = True
        ger = next((u for u in unidades if (u.get("tipoUnidade") or "") == "GERENCIADORA"),
                   unidades[0] if unidades else None)
        if ger:
            it["_saldoAdesoes"] = _num(ger.get("saldoAdesoes"))
            it["_qtdLimiteAdesao"] = _num(ger.get("qtdLimiteAdesao"))
            it["_aceitaAdesao"] = bool(ger.get("aceitaAdesao"))
            it["_saldoEmpenho"] = _num(ger.get("saldoRemanejamentoEmpenho"))
        else:
            # Sem registro de unidade: o item nao esta habilitado para adesao.
            it["_saldoAdesoes"] = 0.0
            it["_qtdLimiteAdesao"] = 0.0
            it["_aceitaAdesao"] = False
            it["_saldoEmpenho"] = 0.0
        if i % 10 == 0:
            log(f"      {i}/{len(alvos)}...")

    for it in candidatos[limite:]:
        it["_saldoConsultado"] = False
    return candidatos


def montar_linhas(candidatos: list[dict], *, necessidade: float | None = None,
                  so_disponiveis: bool = True) -> list[dict]:
    """Achata para a planilha e calcula a quantidade sugerida de adesao.

    Regra de quantidade (Decreto 11.462/2023, arts. 31-32 -- CONFERIR o texto
    vigente antes de usar como corte formal):
      - o total de adesoes do item nao pode passar do dobro do registrado
        (`qtdLimiteAdesao`, que a API ja entrega calculado);
      - `saldoAdesoes` e o quanto desse teto ainda sobra;
      - cada orgao nao participante fica limitado a 50% do quantitativo registrado.
    """
    linhas: list[dict] = []
    for it in candidatos:
        consultado = it.get("_saldoConsultado", False)
        saldo = it.get("_saldoAdesoes")
        aceita = it.get("_aceitaAdesao")

        if so_disponiveis and consultado and (not aceita or not saldo):
            continue

        registrada = _num(it.get("quantidadeHomologadaVencedor")) or \
            _num(it.get("quantidadeHomologadaItem"))
        teto_por_orgao = 0.5 * registrada
        # Sem consultar o saldo nao ha como sugerir quantidade: o teto legal
        # sozinho diria quanto CABERIA, nao quanto ainda esta disponivel.
        if consultado:
            limites = [v for v in (saldo, teto_por_orgao, necessidade) if v]
            sugerida = min(limites) if limites else None
        else:
            sugerida = None

        cnpj = it.get("niFornecedor") or ""
        linhas.append({
            "CATMAT": it.get("codigoItem"),
            "Descricao": (it.get("descricaoItem") or "").strip(),
            "Tipo": it.get("tipoItem"),
            "UASG gerenciadora": it.get("codigoUnidadeGerenciadora"),
            "Orgao gerenciador": it.get("nomeUnidadeGerenciadora"),
            "Ata": it.get("numeroAtaRegistroPreco"),
            "Compra/Ano": f"{it.get('numeroCompra')}/{it.get('anoCompra')}",
            "Modalidade": it.get("nomeModalidadeCompra"),
            "Item": str(it.get("numeroItem") or "").zfill(LARGURA_NUMERO_ITEM),
            "Fornecedor": it.get("nomeRazaoSocialFornecedor"),
            "CNPJ": cnpj,
            "SICAF": "regular" if str(it.get("situacaoSicaf")) == "1" else it.get("situacaoSicaf"),
            "Valor unitario": _num(it.get("valorUnitario")),
            "Qtd registrada": registrada,
            "Qtd empenhada": _num(it.get("quantidadeEmpenhada")),
            "Limite adesao": it.get("_qtdLimiteAdesao") if consultado else _num(it.get("maximoAdesao")),
            "Saldo adesao": saldo if consultado else None,
            "Aceita adesao": aceita if consultado else None,
            "Qtd sugerida": sugerida,
            "Vigencia final": it.get("dataVigenciaFinal"),
            "Dias restantes": it.get("_diasRestantes"),
            "Saldo consultado": consultado,
            "Link PNCP": _link_pncp(it),
        })

    # Mais vantajoso primeiro: menor preco unitario, depois maior saldo e vigencia.
    linhas.sort(key=lambda r: (r["Valor unitario"] or 9e18,
                               -(r["Saldo adesao"] or 0),
                               -(r["Dias restantes"] or 0)))
    return linhas


def _link_pncp(it: dict) -> str:
    """A API de item nao traz o link da ata; ele e reconstruivel pelo id de controle.

    Formato do id: "<cnpj>-1-<sequencial>/<ano>-<sequencialAta>".
    """
    controle = it.get("numeroControlePncpAta") or ""
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})-(\d+)$", controle)
    if not m:
        return ""
    cnpj, seq, ano, seq_ata = m.groups()
    return (f"https://pncp.gov.br/app/atas/{cnpj}/{ano}/"
            f"{int(seq)}/{int(seq_ata)}")
