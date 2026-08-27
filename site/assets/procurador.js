"use strict";
// Aba Procurador — busca ao vivo no PNCP, direto do navegador.
//
// Só é possível porque a API do PNCP manda `Access-Control-Allow-Origin: *`
// (verificado). É o contrário da API do Compras.gov.br, que não manda o
// cabeçalho e por isso obrigou os dados pré-gerados da aba Adesão.

const UFS = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG",
             "PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"];

const PROC_POR_PAGINA = 20;

let procPagina = 1, procTotal = 0, procCarregando = false;

function montarUrlPncp(pagina) {
  const p = new URLSearchParams();
  // `tipos_documento` é OBRIGATÓRIO: sem ele a API devolve corpo VAZIO com
  // HTTP 200 -- falha silenciosa que pareceria "nenhum resultado".
  p.set("tipos_documento", $("#proc-tipo").value || "edital");
  p.set("pagina", pagina);
  p.set("tam_pagina", PROC_POR_PAGINA);
  p.set("ordenacao", "-data");
  const q = $("#proc-q").value.trim();
  if (q) p.set("q", q);
  const status = $("#proc-status").value;
  if (status) p.set("status", status);
  const uf = $("#proc-uf").value;
  if (uf) p.set("ufs", uf);
  const esfera = $("#proc-esfera").value;
  if (esfera) p.set("esferas", esfera);
  return `${CONFIG.PNCP_BUSCA}?${p}`;
}

function linhaPncp(it) {
  const local = [it.municipio_nome, it.uf].filter(Boolean).join(" / ");
  const link = it.item_url ? "https://pncp.gov.br" + it.item_url : "";
  const fim = it.data_fim_vigencia ? diasAte(it.data_fim_vigencia) : null;
  const adesao = it.permite_adesao
    ? `<br><span class="etiqueta et-ok" title="Esta ata admite carona">permite adesão</span>`
    : "";
  return `<tr>
    <td>
      <b>${escaparHtml(it.title || "—")}</b><br>
      <span class="menor">${escaparHtml((it.description || "").slice(0, 220))}</span>
      ${adesao}
    </td>
    <td>${escaparHtml(it.orgao_nome || "—")}<br>
        <span class="menor">${escaparHtml(it.unidade_nome || "")}</span></td>
    <td>${escaparHtml(it.modalidade_licitacao_nome || "—")}<br>
        <span class="menor">${escaparHtml(it.esfera_nome || "")}</span></td>
    <td>${escaparHtml(it.situacao_nome || "—")}
        ${fim != null ? `<br><span class="menor${fim < 0 ? " et-curto" : ""}">
           vigência até ${dia(it.data_fim_vigencia)}</span>` : ""}</td>
    <td class="num">${it.valor_global ? moeda(it.valor_global) : "—"}</td>
    <td>${escaparHtml(local || "—")}</td>
    <td class="num">${link
      ? `<a href="${escaparHtml(link)}" target="_blank" rel="noopener">Abrir</a>` : ""}</td>
  </tr>`;
}

async function pesquisarPncp(novaBusca = true) {
  if (procCarregando) return;
  procCarregando = true;
  limparErro("#erro-proc");
  if (novaBusca) { procPagina = 1; $("#proc-corpo").innerHTML = ""; }
  $("#proc-resumo").innerHTML = `<span class="carregando"></span>Consultando o PNCP…`;
  $("#proc-mais").hidden = true;

  try {
    const d = await buscarJson(montarUrlPncp(procPagina),
                               { tentativas: CONFIG.TENTATIVAS });
    const itens = d.items || [];
    procTotal = d.total || 0;
    $("#proc-corpo").insertAdjacentHTML("beforeend", itens.map(linhaPncp).join(""));
    const mostrados = $("#proc-corpo").children.length;
    $("#proc-resumo").textContent = procTotal
      ? `${num(procTotal)} resultados · mostrando ${num(mostrados)}`
      : "Nenhum resultado.";
    $("#proc-vazio").hidden = procTotal > 0;
    $("#proc-mais").hidden = mostrados >= procTotal || itens.length === 0;
  } catch (e) {
    // Nunca dizer "nenhum resultado" quando a consulta falhou: o PNCP derruba
    // conexões em rajada, e confundir as duas coisas esconde a licitação.
    $("#proc-resumo").textContent = "";
    $("#proc-vazio").hidden = true;
    mostrarErro("#erro-proc",
      "Não consegui consultar o PNCP agora — isto não quer dizer que não haja resultados.",
      `Tente de novo em alguns segundos. (${e.message})`);
  } finally {
    procCarregando = false;
  }
}

function iniciarProcurador() {
  $("#proc-uf").insertAdjacentHTML("beforeend",
    UFS.map(u => `<option value="${u}">${u}</option>`).join(""));

  $("#proc-buscar").addEventListener("click", () => pesquisarPncp(true));
  $("#proc-q").addEventListener("keydown", e => {
    if (e.key === "Enter") pesquisarPncp(true);
  });
  // Atraso ao digitar: a API recusa rajadas, então uma busca por tecla a
  // derrubaria em segundos.
  $("#proc-q").addEventListener("input",
    atrasar(() => { if ($("#proc-q").value.trim().length >= 3) pesquisarPncp(true); },
            CONFIG.DEBOUNCE_MS));
  ["#proc-tipo", "#proc-status", "#proc-uf", "#proc-esfera"].forEach(s =>
    $(s).addEventListener("change", () => pesquisarPncp(true)));
  $("#proc-mais").addEventListener("click", () => { procPagina++; pesquisarPncp(false); });
}
