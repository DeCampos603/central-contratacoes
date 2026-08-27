"use strict";
// Utilitários compartilhados pelas três abas.

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const semAcento = s => (s || "").normalize("NFD")
  .replace(/[̀-ͯ]/g, "").toLowerCase();

const escaparRegex = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const escaparHtml = s => String(s == null ? "" : s)
  .replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
                               '"': "&quot;", "'": "&#39;" }[c]));

const moeda = n => (n == null ? "—" : n.toLocaleString("pt-BR",
  { style: "currency", currency: "BRL", minimumFractionDigits: 2,
    maximumFractionDigits: 4 }));

const num = n => (n == null ? "—" : n.toLocaleString("pt-BR",
  { maximumFractionDigits: 2 }));

const dia = s => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : (s || "—");
};

const diasAte = s => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
  if (!m) return null;
  const alvo = new Date(+m[1], +m[2] - 1, +m[3]);
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  return Math.round((alvo - hoje) / 86400000);
};

const cnpjFormatado = c => {
  const d = String(c || "").replace(/\D/g, "");
  return d.length === 14
    ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")
    : (c || "");
};

function atrasar(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/**
 * GET com repetição. Existe porque os dois serviços de que o site depende
 * falham de formas diferentes e igualmente traiçoeiras:
 *  - o PNCP derrruba conexões em rajada (medido: pedidos seguidos voltaram vazios);
 *  - o Render hiberna no plano gratuito e a primeira chamada paga a partida.
 * Em ambos, tratar a falha como "nada encontrado" seria mentir para o usuário.
 */
async function buscarJson(url, { tentativas = 2, timeoutMs = 90000 } = {}) {
  let ultimoErro;
  for (let i = 0; i < tentativas; i++) {
    const abortador = new AbortController();
    const relogio = setTimeout(() => abortador.abort(), timeoutMs);
    try {
      const r = await fetch(url, { signal: abortador.signal });
      const texto = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      // Corpo vazio com HTTP 200 é o sintoma do PNCP recusando a chamada.
      // Não é "zero resultados" -- é falha, e precisa ser tratada como tal.
      if (!texto.trim()) throw new Error("resposta vazia");
      return JSON.parse(texto);
    } catch (e) {
      ultimoErro = e;
      if (i < tentativas - 1) await new Promise(r => setTimeout(r, 1200 * (i + 1)));
    } finally {
      clearTimeout(relogio);
    }
  }
  throw ultimoErro;
}

function mostrarErro(seletor, mensagem, detalhe) {
  const el = $(seletor);
  if (!el) return;
  el.hidden = false;
  el.className = "aviso aviso-erro";
  el.innerHTML = `<b>${escaparHtml(mensagem)}</b>` +
    (detalhe ? ` <span class="menor">${escaparHtml(detalhe)}</span>` : "");
}

function limparErro(seletor) {
  const el = $(seletor);
  if (el) { el.hidden = true; el.innerHTML = ""; }
}

// ------------------------------------------------------------------- abas
function iniciarAbas() {
  const botoes = $$(".abas button[role=tab]");
  const trocar = (id, comHash = true) => {
    botoes.forEach(b => {
      const ativo = b.dataset.aba === id;
      b.setAttribute("aria-selected", ativo);
      b.tabIndex = ativo ? 0 : -1;
      const painel = document.getElementById("painel-" + b.dataset.aba);
      if (painel) painel.hidden = !ativo;
    });
    if (comHash) history.replaceState(null, "", "#" + id);
    document.dispatchEvent(new CustomEvent("aba:ativa", { detail: id }));
  };
  botoes.forEach(b => b.addEventListener("click", () => trocar(b.dataset.aba)));
  // Setas navegam entre abas, como manda o padrão de tablist.
  $(".abas").addEventListener("keydown", e => {
    const i = botoes.findIndex(b => b.getAttribute("aria-selected") === "true");
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const j = (i + (e.key === "ArrowRight" ? 1 : -1) + botoes.length) % botoes.length;
    botoes[j].focus(); trocar(botoes[j].dataset.aba);
  });
  const inicial = location.hash.replace("#", "");
  trocar(botoes.some(b => b.dataset.aba === inicial) ? inicial : botoes[0].dataset.aba,
         false);
  return trocar;
}
