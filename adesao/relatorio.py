# -*- coding: utf-8 -*-
"""Saida: tabela no console e planilha .xlsx."""

from __future__ import annotations

from pathlib import Path

COLUNAS_CONSOLE = [
    ("CATMAT", 8), ("Descricao", 46), ("UASG gerenciadora", 8), ("Ata", 11),
    ("Item", 6), ("Fornecedor", 26), ("Valor unitario", 12),
    ("Saldo adesao", 13), ("Qtd sugerida", 12), ("Dias restantes", 6),
]


def _fmt(valor, largura: int, coluna: str) -> str:
    if valor is None:
        # Nessas duas colunas, vazio significa "nao consultado" -- e nao zero.
        texto = "?" if coluna in ("Saldo adesao", "Qtd sugerida") else "-"
    elif coluna in ("Valor unitario",):
        texto = f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    elif coluna in ("Saldo adesao", "Qtd sugerida"):
        texto = f"{valor:,.0f}".replace(",", ".")
    else:
        texto = str(valor)
    texto = texto.replace("\n", " ")
    if len(texto) > largura:
        texto = texto[: largura - 1] + "…"
    alinhar_direita = coluna in ("Valor unitario", "Saldo adesao",
                                 "Qtd sugerida", "Dias restantes")
    return texto.rjust(largura) if alinhar_direita else texto.ljust(largura)


def imprimir_console(linhas: list[dict], top: int = 25, log=print) -> None:
    if not linhas:
        log("\nNenhum item disponivel para adesao com esses filtros.")
        return
    cabecalho = "  ".join(nome.ljust(l)[:l] for nome, l in COLUNAS_CONSOLE)
    log("")
    log(cabecalho)
    log("-" * len(cabecalho))
    for r in linhas[:top]:
        log("  ".join(_fmt(r.get(nome), l, nome) for nome, l in COLUNAS_CONSOLE))
    if len(linhas) > top:
        log(f"... e mais {len(linhas) - top} itens (veja a planilha).")

    nao_consultados = sum(1 for r in linhas if not r.get("Saldo consultado"))
    if nao_consultados:
        log(f"\nAviso: {nao_consultados} itens sairam SEM consulta de saldo "
            f"(--limite). 'Saldo adesao' vazio significa nao verificado, "
            f"nao significa zero.")


def salvar_xlsx(linhas: list[dict], caminho: str | Path) -> Path:
    import pandas as pd

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(linhas)
    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Adesao")
        planilha = writer.sheets["Adesao"]
        larguras = {"Descricao": 60, "Fornecedor": 34, "Orgao gerenciador": 30,
                    "Link PNCP": 44}
        for i, coluna in enumerate(df.columns, start=1):
            letra = planilha.cell(row=1, column=i).column_letter
            planilha.column_dimensions[letra].width = larguras.get(coluna, 16)
        planilha.freeze_panes = "A2"
    return caminho
