# -*- coding: utf-8 -*-
"""Gera os dados estaticos do site de busca de itens para adesao.

Por que existem dados pre-gerados em vez de o site chamar a API direto: a API do
Compras.gov.br NAO envia `Access-Control-Allow-Origin`. A resposta chega com
HTTP 200 e cabecalho `Vary: Origin`, mas sem ACAO -- ou seja, o navegador bloqueia
a leitura. Site estatico no GitHub Pages nao consegue consumi-la. Entao um job
(Actions ou local) varre a API por fora e publica JSON.

Volume medido em 26/08/2026: 137.830 atas com vigencia final futura, media de
6,2 itens por ata -- da ordem de 850 mil itens. Nao cabe num JSON unico, entao os
dados sao fatiados por PDM (o agrupador do catalogo: "GAS COMPRIMIDO",
"ARMARIO ACO"...). O site carrega so a fatia do PDM que o usuario escolheu.

Uso:
    python gerar_site.py --meses 24                 # varredura nacional completa
    python gerar_site.py --meses 1                  # amostra rapida, para testar
    python gerar_site.py --pdm 14936 --pdm 309      # so alguns PDMs
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from adesao.api import Cliente
from adesao.busca import _data, _num, LARGURA_NUMERO_ITEM

DIR_SITE = Path("site")
DIR_DADOS = DIR_SITE / "data"


def _link_pncp(controle: str) -> str:
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})-(\d+)$", controle or "")
    if not m:
        return ""
    cnpj, seq, ano, seq_ata = m.groups()
    return f"https://pncp.gov.br/app/atas/{cnpj}/{ano}/{int(seq)}/{int(seq_ata)}"


# Palavras que aparecem em quase toda descricao do catalogo e nao ajudam a achar
# nada -- ficam de fora dos termos de busca de cada grupo.
_RUIDO = {
    "material", "tipo", "cor", "aplicacao", "modelo", "medidas", "dimensoes",
    "caracteristica", "caracteristicas", "adicional", "adicionais", "componentes",
    "formato", "capacidade", "comprimento", "largura", "altura", "espessura",
    "peso", "volume", "unidade", "quantidade", "acabamento", "superficial",
    "tratamento", "revestimento", "apresentacao", "composicao", "basica",
    "referencia", "numero", "grau", "pureza", "aspecto", "fisico", "formula",
    "quimica", "massa", "molecular", "nome", "para", "com", "sem", "uso",
    "outros", "demais", "conforme", "aproximadas", "aproximada", "und",
}


def _termos_do_grupo(descricoes: list[str], maximo: int = 30) -> list[str]:
    """Palavras mais frequentes das descricoes, para a busca achar o grupo.

    Sem isso, procurar "oxigenio" nao acha nada: o PDM se chama "GAS COMPRIMIDO"
    e a palavra que o usuario digita mora na descricao do item, nao no nome do
    grupo. Foi o primeiro tropeco no teste da interface.
    """
    contagem: dict[str, int] = defaultdict(int)
    for texto in descricoes:
        # Alem de palavras de 4+ letras, captura formatos curtos que a pessoa
        # digita ("a4", "a3", "m3", "70g") -- sem isso "papel a4" nao achava nada.
        achadas = re.findall(r"[a-z]{4,}|[a-z]\d+|\d+[a-z]+", _sem_acento(texto))
        for palavra in set(achadas):
            if palavra not in _RUIDO:
                contagem[palavra] += 1
    ordenadas = sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    return [palavra for palavra, _ in ordenadas[:maximo]]


def _sem_acento(texto: str) -> str:
    d = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in d if not unicodedata.combining(c)).lower()


def _compra(it: dict) -> str:
    """`numeroCompra`/`anoCompra` faltam em parte dos registros. Sem valor, vazio."""
    numero, ano = it.get("numeroCompra"), it.get("anoCompra")
    if not numero and not ano:
        return ""
    return f"{numero or '?'}/{ano or '?'}"


def coletar(cli: Cliente, *, meses: int, dias_min: int, pdms: list[int] | None,
            uasgs: list[str] | None, hoje: date, log=print) -> list[dict]:
    """Varre `2_consultarARPItem` e devolve os itens ainda vigentes."""
    inicio = (hoje - timedelta(days=int(meses * 30.5))).isoformat()
    fim = hoje.isoformat()
    corte = hoje + timedelta(days=dias_min)

    consultas: list[dict] = []
    for p in (pdms or []):
        consultas.append({"codigoPdm": int(p)})
    for u in (uasgs or []):
        consultas.append({"codigoUnidadeGerenciadora": int(u)})
    if not consultas:
        consultas.append({})

    brutos: list[dict] = []
    for filtros in consultas:
        rotulo = ", ".join(f"{k}={v}" for k, v in filtros.items()) or "varredura nacional"
        log(f"[coleta] {rotulo} (vigencia inicial {inicio} a {fim})...")
        t0 = time.time()
        brutos.extend(cli.itens_arp(inicio, fim, **filtros))
        log(f"          {len(brutos)} itens acumulados em {time.time()-t0:.0f}s")

    vistos: set[tuple] = set()
    vigentes: list[dict] = []
    for it in brutos:
        if it.get("itemExcluido"):
            continue
        fim_vig = _data(it.get("dataVigenciaFinal"))
        if not fim_vig or fim_vig < corte:
            continue
        chave = (it.get("numeroControlePncpAta"), it.get("numeroItem"),
                 it.get("niFornecedor"))
        if chave in vistos:
            continue
        vistos.add(chave)
        it["_diasRestantes"] = (fim_vig - hoje).days
        vigentes.append(it)

    log(f"[coleta] {len(vigentes)} itens vigentes por >= {dias_min} dias "
        f"(de {len(brutos)} brutos).")
    return vigentes


def enriquecer(cli: Cliente, itens: list[dict], limite: int, *, threads: int = 6,
               log=print) -> int:
    """Anota saldoAdesoes/aceitaAdesao nos `limite` itens mais baratos.

    Sequencial isso mede ~8,7 s por item (o endpoint costuma responder em 0,2 s
    mas trava por dezenas de segundos de vez em quando), o que nao cabe num job
    diario. Como as travadas sao de espera, nao de CPU, algumas threads resolvem:
    enquanto uma pena, as outras avancam.

    Itens nao enriquecidos ficam SEM a chave `_saldo` e vao para o site como
    "nao verificado" -- nunca como zero.
    """
    alvos = sorted(itens, key=lambda it: _num(it.get("valorUnitario")) or 9e18)[:limite]
    if not alvos:
        return 0
    log(f"[saldo] consultando o saldo real de {len(alvos)} itens "
        f"({threads} threads)...")
    t0 = time.time()
    feitos = 0
    trava = threading.Lock()

    def tarefa(it: dict) -> bool:
        try:
            unidades = cli.unidades_item(
                it.get("numeroAtaRegistroPreco"), it.get("codigoUnidadeGerenciadora"),
                str(it.get("numeroItem") or "").zfill(LARGURA_NUMERO_ITEM))
        except Exception:
            return False
        ger = next((u for u in unidades
                    if (u.get("tipoUnidade") or "") == "GERENCIADORA"),
                   unidades[0] if unidades else None)
        it["_saldo"] = _num(ger.get("saldoAdesoes")) if ger else 0.0
        it["_aceita"] = bool(ger.get("aceitaAdesao")) if ger else False
        return True

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        for ok in pool.map(tarefa, alvos):
            with trava:
                feitos += 1 if ok else 0
                total = feitos
            if total and total % 200 == 0:
                log(f"        {total}/{len(alvos)} ({time.time()-t0:.0f}s)")

    dur = time.time() - t0
    log(f"[saldo] {feitos} itens verificados em {dur:.0f}s "
        f"({dur/max(1,len(alvos)):.1f}s por item).")
    return feitos


def escrever(itens: list[dict], *, hoje: date, log=print) -> dict:
    """Grava indice.json e uma fatia por PDM. Devolve o resumo."""
    if DIR_DADOS.exists():
        shutil.rmtree(DIR_DADOS)
    (DIR_DADOS / "pdm").mkdir(parents=True, exist_ok=True)

    por_pdm: dict[int, list[dict]] = defaultdict(list)
    for it in itens:
        por_pdm[int(it.get("codigoPdm") or 0)].append(it)

    indice = []
    total_bytes = 0
    for cod_pdm, lista in sorted(por_pdm.items()):
        # Dicionarios locais: descricoes, fornecedores e unidades repetem muito.
        descricoes, fornecedores, unidades = {}, {}, {}

        def idx(dicionario: dict, chave, valor):
            if chave not in dicionario:
                dicionario[chave] = (len(dicionario), valor)
            return dicionario[chave][0]

        linhas = []
        for it in lista:
            i_desc = idx(descricoes, (it.get("descricaoItem") or "").strip(),
                         (it.get("descricaoItem") or "").strip())
            i_forn = idx(fornecedores, it.get("niFornecedor") or "",
                         [it.get("niFornecedor") or "",
                          it.get("nomeRazaoSocialFornecedor") or ""])
            i_uni = idx(unidades, str(it.get("codigoUnidadeGerenciadora") or ""),
                        [str(it.get("codigoUnidadeGerenciadora") or ""),
                         it.get("nomeUnidadeGerenciadora") or ""])
            saldo = it.get("_saldo")
            linhas.append([
                it.get("codigoItem"), i_desc, i_uni, i_forn,
                it.get("numeroAtaRegistroPreco"),
                str(it.get("numeroItem") or "").zfill(LARGURA_NUMERO_ITEM),
                round(_num(it.get("valorUnitario")), 4),
                _num(it.get("quantidadeHomologadaVencedor")) or _num(it.get("quantidadeHomologadaItem")),
                _num(it.get("maximoAdesao")),
                _num(it.get("quantidadeEmpenhada")),
                it.get("dataVigenciaFinal"), it.get("_diasRestantes"),
                # 81 de 764 itens numa amostra vieram sem numeroCompra/anoCompra;
                # a f-string ingenua gravava a string "None/None" na planilha.
                _compra(it),
                it.get("nomeModalidadeCompra"),
                _link_pncp(it.get("numeroControlePncpAta") or ""),
                # None = saldo nao verificado. Nunca confundir com zero.
                None if saldo is None else round(saldo, 2),
                it.get("_aceita"),
            ])

        def ordenar(dicionario):
            return [v for _, v in sorted(dicionario.values(), key=lambda t: t[0])]

        pacote = {
            "pdm": cod_pdm,
            "nome": lista[0].get("nomePdm") or "",
            "d": ordenar(descricoes),
            "f": ordenar(fornecedores),
            "u": ordenar(unidades),
            "itens": linhas,
        }
        # JSON puro de proposito: o GitHub Pages ja comprime as respostas de
        # texto na entrega, e assim o site tambem abre por file:// sem depender
        # de DecompressionStream.
        caminho = DIR_DADOS / "pdm" / f"{cod_pdm}.json"
        caminho.write_text(json.dumps(pacote, ensure_ascii=False,
                                      separators=(",", ":")), encoding="utf-8")
        total_bytes += caminho.stat().st_size

        # So conta preco de item que admite carona -- "a partir de R$ X" para um
        # item vedado nao ajuda ninguem.
        aderiveis = [it for it in lista if _num(it.get("maximoAdesao")) > 0]
        precos = [_num(it.get("valorUnitario")) for it in aderiveis
                  if _num(it.get("valorUnitario")) > 0]
        indice.append([
            cod_pdm, lista[0].get("nomePdm") or "", len(lista),
            len({it.get("numeroControlePncpAta") for it in lista}),
            round(min(precos), 2) if precos else None,
            sum(1 for it in lista if it.get("_saldo")),
            " ".join(_termos_do_grupo(pacote["d"])),
            len(aderiveis),
        ])

    indice.sort(key=lambda r: -r[7])   # mais itens ADERIVEIS primeiro
    resumo = {
        "gerado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "referencia": hoje.isoformat(),
        "totalItens": len(itens),
        "totalAtas": len({it.get("numeroControlePncpAta") for it in itens}),
        "totalPdms": len(por_pdm),
        # ~47% dos itens vem com maximoAdesao 0: a ata nao admite carona. Contar
        # so o total esconderia que metade da base nao serve para adesao.
        "totalAderiveis": sum(1 for it in itens if _num(it.get("maximoAdesao")) > 0),
        "comSaldoVerificado": sum(1 for it in itens if it.get("_saldo") is not None),
        "pdms": indice,
    }
    alvo = DIR_DADOS / "indice.json"
    alvo.write_text(json.dumps(resumo, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")

    mb = (total_bytes + alvo.stat().st_size) / 1024 / 1024
    log(f"[site] {len(por_pdm)} fatias de PDM + indice = {mb:.1f} MB em {DIR_DADOS}")
    return resumo


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--meses", type=int, default=24,
                   help="janela retroativa de inicio de vigencia (padrao: 24)")
    p.add_argument("--dias-min", type=int, default=30,
                   help="vigencia restante minima, em dias (padrao: 30)")
    p.add_argument("--pdm", type=int, action="append", help="restringe a PDMs")
    p.add_argument("--uasg", action="append", help="restringe a UASGs gerenciadoras")
    p.add_argument("--saldo", type=int, default=0,
                   help="quantos itens tem o saldo real verificado (padrao: 0)")
    p.add_argument("--threads", type=int, default=6,
                   help="threads na verificacao de saldo (padrao: 6)")
    p.add_argument("--cache", default="cache")
    p.add_argument("--ttl", type=float, default=6.0)
    args = p.parse_args(argv)

    cli = Cliente(dir_cache=args.cache, ttl_horas=args.ttl)
    hoje = date.today()
    itens = coletar(cli, meses=args.meses, dias_min=args.dias_min,
                    pdms=args.pdm, uasgs=args.uasg, hoje=hoje)
    if not itens:
        print("Nada coletado.", file=sys.stderr)
        return 1
    if args.saldo:
        enriquecer(cli, itens, args.saldo, threads=args.threads)
    resumo = escrever(itens, hoje=hoje)
    print(f"\nOK: {resumo['totalItens']} itens, {resumo['totalAtas']} atas, "
          f"{resumo['totalPdms']} PDMs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
