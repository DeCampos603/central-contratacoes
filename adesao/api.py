# -*- coding: utf-8 -*-
"""Cliente da API publica de dados abertos do Compras.gov.br (modulo-arp).

Nenhuma autenticacao e necessaria. Regras aprendidas em teste real contra o
servico (26/08/2026) e que este modulo respeita:

- `tamanhoPagina` SO aceita 10..500. Fora disso volta HTTP 400 com o texto
  "Informe um numero de paginacao no intervalo de 10 a 500".
- O envelope de resposta e sempre
  {"resultado": [...], "totalRegistros": n, "totalPaginas": n, "paginasRestantes": n}.
- Uma pagina de 500 itens de `2_consultarARPItem` volta em ~1,3 s.
- `3_consultarUnidadesItem` e `4_consultarEmpenhosSaldoItem` sao MUITO lentos
  (>90 s, as vezes >200 s). Dai o timeout separado e o cache em disco.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://dadosabertos.compras.gov.br"

# Endpoints do modulo de Atas de Registro de Precos.
EP_ATAS = "/modulo-arp/1_consultarARP"
EP_ATAS_FIM_VIGENCIA = "/modulo-arp/1.2_consultarARP_FimVigencia"
EP_ITENS = "/modulo-arp/2_consultarARPItem"
EP_ITENS_DA_ATA = "/modulo-arp/2.1_consultarARPItem_Id"
EP_UNIDADES_ITEM = "/modulo-arp/3_consultarUnidadesItem"
EP_EMPENHOS_ITEM = "/modulo-arp/4_consultarEmpenhosSaldoItem"
EP_ADESOES_ITEM = "/modulo-arp/5_consultarAdesoesItem"
EP_CATMAT = "/modulo-material/4_consultarItemMaterial"

# Os endpoints 3/4/5 sao por-ata e lentos; os demais respondem em segundos.
_LENTOS = (EP_UNIDADES_ITEM, EP_EMPENHOS_ITEM, EP_ADESOES_ITEM)

TAM_PAGINA_MAX = 500
TAM_PAGINA_MIN = 10

USER_AGENT = "AgenteAdesaoARP/1.0 (+uso interno BCMS)"


class ApiErro(RuntimeError):
    pass


class Cliente:
    """Cliente com paginacao, backoff e cache em disco.

    O cache e por (endpoint, parametros) e vale `ttl_horas`. Sem ele, refazer
    uma busca custa os mesmos minutos da primeira vez.
    """

    def __init__(self, dir_cache: Path | str = "cache", ttl_horas: float = 12.0,
                 pausa_s: float = 0.15, log=print):
        self.dir_cache = Path(dir_cache)
        self.dir_cache.mkdir(parents=True, exist_ok=True)
        self.ttl_s = ttl_horas * 3600
        self.pausa_s = pausa_s
        self.log = log

    # ---------------------------------------------------------------- cache
    def _caminho_cache(self, endpoint: str, params: dict) -> Path:
        chave = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        nome = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:20]
        return self.dir_cache / f"{nome}.json"

    def _ler_cache(self, caminho: Path):
        if not caminho.exists():
            return None
        if self.ttl_s and (time.time() - caminho.stat().st_mtime) > self.ttl_s:
            return None
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ----------------------------------------------------------------- http
    def _get(self, endpoint: str, params: dict, tentativas: int = 4) -> dict:
        caminho = self._caminho_cache(endpoint, params)
        em_cache = self._ler_cache(caminho)
        if em_cache is not None:
            return em_cache

        url = f"{BASE}{endpoint}?" + urllib.parse.urlencode(params)
        timeout = 300 if endpoint in _LENTOS else 90
        espera = 4.0
        for tentativa in range(1, tentativas + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"accept": "*/*", "User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    dados = json.loads(resp.read().decode("utf-8"))
                caminho.write_text(json.dumps(dados, ensure_ascii=False),
                                   encoding="utf-8")
                time.sleep(self.pausa_s)
                return dados
            except urllib.error.HTTPError as e:
                corpo = ""
                try:
                    corpo = e.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
                # 400 e erro de parametro: repetir nao ajuda.
                if e.code == 400:
                    raise ApiErro(f"HTTP 400 em {endpoint}: {corpo}") from None
                if tentativa == tentativas:
                    raise ApiErro(f"HTTP {e.code} em {endpoint}: {corpo}") from None
                self.log(f"  HTTP {e.code}; nova tentativa em {espera:.0f}s")
            except Exception as e:
                if tentativa == tentativas:
                    raise ApiErro(f"falha em {endpoint}: {e}") from None
                self.log(f"  {type(e).__name__}; nova tentativa em {espera:.0f}s")
            time.sleep(espera)
            espera = min(espera * 2, 60)
        raise ApiErro("inalcancavel")

    # ------------------------------------------------------------ paginacao
    def paginar(self, endpoint: str, params: dict, tam_pagina: int = TAM_PAGINA_MAX,
                max_paginas: int = 0, rotulo: str = "") -> list[dict]:
        """Percorre todas as paginas e devolve a lista concatenada de resultados."""
        tam_pagina = max(TAM_PAGINA_MIN, min(TAM_PAGINA_MAX, tam_pagina))
        saida: list[dict] = []
        pagina = 1
        total_paginas = None
        while True:
            p = dict(params, pagina=pagina, tamanhoPagina=tam_pagina)
            dados = self._get(endpoint, p)
            lote = dados.get("resultado") or []
            saida.extend(lote)
            if total_paginas is None:
                total_paginas = int(dados.get("totalPaginas") or 0)
                if rotulo and total_paginas > 1:
                    self.log(f"  {rotulo}: {dados.get('totalRegistros')} registros "
                             f"em {total_paginas} paginas")
            if not lote or total_paginas is None or pagina >= total_paginas:
                break
            if max_paginas and pagina >= max_paginas:
                self.log(f"  {rotulo}: parando em {max_paginas} paginas "
                         f"(de {total_paginas}) por limite pedido")
                break
            pagina += 1
        return saida

    # ------------------------------------------------------------ consultas
    def itens_arp(self, vigencia_inicial_min: str, vigencia_inicial_max: str,
                  **filtros) -> list[dict]:
        """2_consultarARPItem. Filtros uteis: codigoItem, codigoPdm,
        codigoUnidadeGerenciadora, niFornecedor, codigoModalidadeCompra,
        numeroCompra, tipoItem.

        ATENCAO: o intervalo obrigatorio e de vigencia INICIAL. A API nao filtra
        por vigencia final -- atas ja vencidas voltam aqui e sao cortadas pelo
        chamador.
        """
        params = {k: v for k, v in filtros.items() if v not in (None, "", [])}
        params["dataVigenciaInicialMin"] = vigencia_inicial_min
        params["dataVigenciaInicialMax"] = vigencia_inicial_max
        return self.paginar(EP_ITENS, params, rotulo="itens ARP")

    def itens_da_ata(self, numero_controle_pncp_ata: str) -> list[dict]:
        """2.1 -- todos os itens de uma ata, com maximoAdesao e quantidadeEmpenhada."""
        return self.paginar(
            EP_ITENS_DA_ATA, {"numeroControlePncpAta": numero_controle_pncp_ata})

    def unidades_item(self, numero_ata: str, unidade_gerenciadora: str,
                      numero_item: str) -> list[dict]:
        """3 -- traz saldoAdesoes, qtdLimiteAdesao e aceitaAdesao. LENTO."""
        return self.paginar(EP_UNIDADES_ITEM, {
            "numeroAta": numero_ata,
            "unidadeGerenciadora": str(unidade_gerenciadora),
            "numeroItem": numero_item,
        }, tam_pagina=TAM_PAGINA_MIN)

    def empenhos_item(self, numero_ata: str, unidade_gerenciadora: str) -> list[dict]:
        """4 -- quantidadeRegistrada/Empenhada/saldoEmpenho por item e unidade. LENTO."""
        return self.paginar(EP_EMPENHOS_ITEM, {
            "numeroAta": numero_ata,
            "unidadeGerenciadora": str(unidade_gerenciadora),
        }, tam_pagina=TAM_PAGINA_MIN)

    def adesoes_item(self, numero_ata: str, unidade_gerenciadora: str,
                     numero_item: str) -> list[dict]:
        """5 -- adesoes ja aprovadas (quantidadeAprovadaAdesao por unidade). LENTO."""
        return self.paginar(EP_ADESOES_ITEM, {
            "numeroAta": numero_ata,
            "unidadeGerenciadora": str(unidade_gerenciadora),
            "numeroItem": numero_item,
        }, tam_pagina=TAM_PAGINA_MIN)

    def catmat_por_classe(self, codigo_classe: int, max_paginas: int = 0) -> list[dict]:
        return self.paginar(EP_CATMAT, {"codigoClasse": codigo_classe},
                            max_paginas=max_paginas,
                            rotulo=f"CATMAT classe {codigo_classe}")

    def catmat_todos(self, max_paginas: int = 0) -> list[dict]:
        return self.paginar(EP_CATMAT, {}, max_paginas=max_paginas,
                            rotulo="CATMAT completo")
