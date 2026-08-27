# -*- coding: utf-8 -*-
"""Indice local do CATMAT, para converter texto livre em codigo de item.

Por que existe: a API NAO faz busca textual. O parametro `descricaoItem` de
`modulo-material/4_consultarItemMaterial` so casa descricao exata -- testado com
"ARMARIO", "ARMÁRIO", "armario" e "OXIGÊNIO", todos com totalRegistros 0. E
`2_consultarARPItem` aceita apenas `codigoItem`/`codigoPdm`, nunca texto.

O catalogo, porem, e enumeravel: 343.880 itens, 500 por pagina (~688 paginas,
~1,3 s cada). Baixamos uma vez e indexamos em SQLite FTS5 -- dai a busca textual
passa a ser local e instantanea.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

from .api import Cliente

CAMINHO_PADRAO = Path("catalogo/catmat.sqlite")


def _sem_acento(texto: str) -> str:
    if not texto:
        return ""
    d = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in d if not unicodedata.combining(c)).lower()


def _conectar(caminho: Path) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(caminho)


def construir(cli: Cliente, caminho: Path | str = CAMINHO_PADRAO, *,
              classes: list[int] | None = None, max_paginas: int = 0,
              log=print) -> Path:
    """Baixa o CATMAT e grava o indice. `classes` restringe a algumas classes."""
    caminho = Path(caminho)
    con = _conectar(caminho)
    con.executescript("""
        DROP TABLE IF EXISTS itens;
        CREATE TABLE itens (
            codigo_item INTEGER PRIMARY KEY,
            codigo_grupo INTEGER, nome_grupo TEXT,
            codigo_classe INTEGER, nome_classe TEXT,
            codigo_pdm INTEGER, nome_pdm TEXT,
            descricao TEXT, busca TEXT, ativo INTEGER
        );
        DROP TABLE IF EXISTS itens_fts;
        CREATE VIRTUAL TABLE itens_fts USING fts5(
            busca, codigo_item UNINDEXED, tokenize='unicode61'
        );
    """)

    if classes:
        lotes = [(f"classe {c}", cli.catmat_por_classe(c, max_paginas=max_paginas))
                 for c in classes]
    else:
        log("Baixando o CATMAT completo (~344 mil itens). Leva alguns minutos...")
        lotes = [("completo", cli.catmat_todos(max_paginas=max_paginas))]

    total = 0
    for rotulo, itens in lotes:
        linhas = []
        for it in itens:
            descricao = (it.get("descricaoItem") or "").strip()
            linhas.append((
                it.get("codigoItem"), it.get("codigoGrupo"), it.get("nomeGrupo"),
                it.get("codigoClasse"), it.get("nomeClasse"),
                it.get("codigoPdm"), it.get("nomePdm"),
                descricao, _sem_acento(f"{it.get('nomePdm') or ''} {descricao}"),
                1 if it.get("statusItem") else 0,
            ))
        con.executemany(
            "INSERT OR REPLACE INTO itens VALUES (?,?,?,?,?,?,?,?,?,?)", linhas)
        total += len(linhas)
        log(f"  {rotulo}: {len(linhas)} itens")

    con.execute("INSERT INTO itens_fts (busca, codigo_item) "
                "SELECT busca, codigo_item FROM itens")
    con.commit()
    con.close()
    log(f"Indice gravado em {caminho} ({total} itens).")
    return caminho


def buscar(texto: str, caminho: Path | str = CAMINHO_PADRAO, *, limite: int = 20,
           so_ativos: bool = True) -> list[dict]:
    """Busca textual local. Todos os termos precisam aparecer (AND)."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(
            f"indice nao encontrado em {caminho}. Rode: "
            f"python buscar_adesao.py catalogo --construir")
    termos = [t for t in _sem_acento(texto).split() if t]
    if not termos:
        return []
    consulta = " AND ".join(f'"{t}"*' for t in termos)
    con = _conectar(caminho)
    con.row_factory = sqlite3.Row
    sql = ("SELECT i.codigo_item, i.descricao, i.codigo_pdm, i.nome_pdm, "
           "       i.codigo_classe, i.nome_classe, i.ativo "
           "FROM itens_fts f JOIN itens i ON i.codigo_item = f.codigo_item "
           "WHERE itens_fts MATCH ? ")
    if so_ativos:
        sql += "AND i.ativo = 1 "
    sql += "LIMIT ?"
    try:
        linhas = [dict(r) for r in con.execute(sql, (consulta, limite))]
    finally:
        con.close()
    return linhas
