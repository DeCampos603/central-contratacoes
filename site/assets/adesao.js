"use strict";
// Aba Adesão — dados pré-gerados por gerar_site.py.
//
// Por que pré-gerado: a API de dados abertos do Compras.gov.br NÃO manda
// `Access-Control-Allow-Origin`. A resposta chega com HTTP 200 e `Vary: Origin`,
// mas sem o cabeçalho — o navegador bloqueia a leitura. É a única aba que
// depende de uma Action; as outras duas consultam ao vivo.

// Formato das linhas gravadas por gerar_site.py (arrays, para o arquivo ficar menor).
const CATMAT = 0, DESC = 1, UNI = 2, FORN = 3, ATA = 4, ITEM = 5, VALOR = 6,
      QTDREG = 7, MAXADESAO = 8, EMPENHADA = 9, VIGFIM = 10, DIAS = 11,
      COMPRA = 12, MODAL = 13, LINK = 14, SALDO = 15, ACEITA = 16;

let adIndice = null, adFatia = null, adLinhas = [], adMarcado = -1;
let adOrdem = { campo: "valor", desc: false };
let adAbrirRaiox = null;   // injetado por iniciarAdesao

// 0 = nenhum casamento (o grupo sai da lista). Cada termo precisa aparecer em
// algum lugar; onde ele aparece define o peso. Ordenar por quantidade de itens
// fazia "cadeira" devolver ROÇADEIRA e ABRAÇADEIRA antes de CADEIRA ESCRITÓRIO.
function pontuar(p, termos) {
  const nome = semAcento(p[1]);
  const extras = semAcento(p[6] || "");
  let total = 0;
  for (const t of termos) {
    const inicioDePalavra = new RegExp("\\b" + escaparRegex(t));
    if (inicioDePalavra.test(nome))        total += 100;
    else if (nome.includes(t))             total += 12;
    else if (inicioDePalavra.test(extras)) total += 10;
    else if (extras.includes(t))           total += 1;
    else return 0;
  }
  return total;
}

async function carregarIndiceAdesao() {
  if (adIndice) return true;
  try {
    adIndice = await buscarJson("data/indice.json", { tentativas: 1 });
  } catch (e) {
    mostrarErro("#erro-adesao", "Não consegui carregar os dados da adesão.",
      "Gere com gerar_site.py ou aguarde a próxima publicação.");
    return false;
  }
  const d = new Date(adIndice.gerado);
  const aderiveis = adIndice.totalAderiveis;
  $("#modo-adesao").textContent = "de " + d.toLocaleDateString("pt-BR");

  const vedados = aderiveis != null ? adIndice.totalItens - aderiveis : null;
  if (adIndice.comSaldoVerificado < adIndice.totalItens) {
    $("#aviso-saldo").hidden = false;
    $("#aviso-saldo").innerHTML =
      `<b>Saldo confirmado em ${num(adIndice.comSaldoVerificado || 0)} de ` +
      `${num(adIndice.totalItens)} itens.</b> Nos demais aparece o <i>limite</i> ` +
      `de adesão, não o saldo remanescente — confirme no Contratos.gov.br antes de pedir.`;
  }
  $("#ad-rodape").innerHTML =
    `${aderiveis != null ? num(aderiveis) + " itens abertos a adesão (de " +
      num(adIndice.totalItens) + " vigentes) · " : ""}` +
    `${num(adIndice.totalAtas)} atas · ${num(adIndice.totalPdms)} grupos · ` +
    `atualizado em ${d.toLocaleString("pt-BR")}.<br>` +
    `Fonte: dados abertos do Compras.gov.br (módulo ARP) — cobre o que está no ` +
    `SIASG: órgãos federais e os entes estaduais/municipais cadastrados nele. ` +
    (vedados ? `<b>Nem toda ata admite carona:</b> ${num(vedados)} itens ` +
      `(${(100 * vedados / adIndice.totalItens).toFixed(1)}%) vieram com limite ` +
      `de adesão zero — ficam ocultos por padrão. ` : "") +
    `Quando a ata admite, o limite é o dobro da quantidade registrada, e cada ` +
    `órgão não participante pode aderir a até 50% do registrado ` +
    `(Decreto 11.462/2023 — confira o texto vigente).`;
  return true;
}

// Texto só de dígitos e pontuação, com 4+ dígitos, é busca por CNPJ.
function digitosDeCnpj(texto) {
  return /^[\d.\/\-\s]+$/.test(texto) ? texto.replace(/\D/g, "") : "";
}

function sugerirPorCnpj(digitos, lista) {
  const achados = (adIndice.fornecedores || [])
    .filter(f => f[0].includes(digitos)).slice(0, 40);
  if (!achados.length) {
    lista.innerHTML = `<li aria-disabled="true"><span class="nome">Nenhum fornecedor com ata aderível para o CNPJ “${
      escaparHtml($("#ad-q").value)}”.</span></li>`;
  } else {
    lista.innerHTML = achados.map(f =>
      `<li role="option" data-cnpj="${f[0]}">
         <span class="nome">${escaparHtml(f[1])}</span>
         <span class="meta">${cnpjFormatado(f[0])} · ${num(f[2])} itens · ${
           f[3].length} grupo${f[3].length > 1 ? "s" : ""}</span>
       </li>`).join("");
  }
  adMarcado = -1;
  lista.hidden = false;
}

function sugerirAdesao() {
  const termos = semAcento($("#ad-q").value).split(/\s+/).filter(Boolean);
  const lista = $("#ad-sugestoes");
  if (!adIndice || !termos.length) { lista.hidden = true; return; }
  const digitos = digitosDeCnpj($("#ad-q").value);
  if (digitos.length >= 4) return sugerirPorCnpj(digitos, lista);
  const achados = adIndice.pdms
    .map(p => [p, pontuar(p, termos)])
    .filter(([, n]) => n > 0)
    .sort((a, b) => (b[1] - a[1]) ||
      ((b[0][7] != null ? b[0][7] : b[0][2]) - (a[0][7] != null ? a[0][7] : a[0][2])))
    .slice(0, 40).map(([p]) => p);
  if (!achados.length) {
    lista.innerHTML = `<li aria-disabled="true"><span class="nome">Nada encontrado para “${
      escaparHtml($("#ad-q").value)}”.</span></li>`;
    lista.hidden = false; return;
  }
  lista.innerHTML = achados.map((p, i) =>
    `<li role="option" data-pdm="${p[0]}" data-i="${i}">
       <span class="nome">${escaparHtml(p[1])}</span>
       <span class="meta">${num(p[7] != null ? p[7] : p[2])} itens${
         p[7] != null ? " abertos" : ""} · ${num(p[3])} atas${
         p[4] != null ? " · a partir de " + moeda(p[4]) : ""}</span>
     </li>`).join("");
  adMarcado = -1;
  lista.hidden = false;
}

async function abrirPdm(codigo, nome) {
  $("#ad-sugestoes").hidden = true;
  $("#ad-q").value = nome;
  $("#ad-resumo").innerHTML = `<span class="carregando"></span>Carregando…`;
  $("#ad-painel").hidden = false;
  try {
    adFatia = await buscarJson(`data/pdm/${encodeURIComponent(codigo)}.json`,
                               { tentativas: 1 });
  } catch (e) {
    $("#ad-resumo").textContent = "";
    mostrarErro("#erro-adesao", "Falha ao carregar este grupo.", e.message);
    return;
  }
  mostrarFatia();
}

// Todos os itens de um fornecedor, juntando as fatias de cada grupo (PDM) em que
// ele aparece. Os dicionários d/u/f de cada fatia são remapeados para um só.
async function abrirFornecedor(cnpj) {
  const reg = (adIndice.fornecedores || []).find(f => f[0] === cnpj);
  if (!reg) return;
  $("#ad-sugestoes").hidden = true;
  $("#ad-q").value = cnpjFormatado(cnpj);
  $("#ad-resumo").innerHTML = `<span class="carregando"></span>Carregando…`;
  $("#ad-painel").hidden = false;
  let fatias;
  try {
    fatias = await Promise.all(reg[3].map(p =>
      buscarJson(`data/pdm/${encodeURIComponent(p)}.json`, { tentativas: 1 })));
  } catch (e) {
    $("#ad-resumo").textContent = "";
    mostrarErro("#erro-adesao", "Falha ao carregar os itens deste fornecedor.", e.message);
    return;
  }
  const d = [], u = [], f = [], itens = [];
  const iD = new Map(), iU = new Map(), iF = new Map();
  const mapa = (m, lista, chave, valor) => {
    if (!m.has(chave)) { m.set(chave, lista.length); lista.push(valor); }
    return m.get(chave);
  };
  for (const fa of fatias) {
    for (const it of fa.itens) {
      const forn = fa.f[it[FORN]];
      if (String(forn[0]).replace(/\D/g, "") !== cnpj) continue;
      const novo = it.slice();
      novo[DESC] = mapa(iD, d, fa.d[it[DESC]], fa.d[it[DESC]]);
      novo[UNI] = mapa(iU, u, fa.u[it[UNI]][0], fa.u[it[UNI]]);
      novo[FORN] = mapa(iF, f, forn[0], forn);
      itens.push(novo);
    }
  }
  adFatia = { nome: "Fornecedor " + reg[1], d, u, f, itens };
  mostrarFatia();
}

function mostrarFatia() {
  limparErro("#erro-adesao");
  preencher("#ad-uasg", adFatia.u, "Todos os órgãos", u => `${u[0]} — ${u[1]}`);
  preencher("#ad-fornecedor", adFatia.f, "Todos os fornecedores", f => f[1] || f[0]);
  $("#ad-filtro").value = ""; $("#ad-dias").value = "0";
  $("#ad-so-saldo").checked = false; $("#ad-incluir-vedados").checked = false;
  adOrdem = { campo: "valor", desc: false };
  desenharAdesao();
}

function preencher(sel, dados, rotuloVazio, formatar) {
  $(sel).innerHTML = `<option value="">${rotuloVazio}</option>` +
    dados.map((d, i) => `<option value="${i}">${escaparHtml(formatar(d))}</option>`).join("");
}

function filtrarAdesao() {
  const termos = semAcento($("#ad-filtro").value).split(/\s+/).filter(Boolean);
  const uasg = $("#ad-uasg").value, forn = $("#ad-fornecedor").value;
  const dias = +$("#ad-dias").value, soSaldo = $("#ad-so-saldo").checked;
  const incluirVedados = $("#ad-incluir-vedados").checked;
  return adFatia.itens.filter(it => {
    // maximoAdesao = 0 significa que a ata NÃO admite carona.
    if (!incluirVedados && !(it[MAXADESAO] > 0)) return false;
    if (uasg !== "" && it[UNI] != uasg) return false;
    if (forn !== "" && it[FORN] != forn) return false;
    if (dias && (it[DIAS] || 0) < dias) return false;
    if (soSaldo && !(it[SALDO] > 0)) return false;
    if (termos.length) {
      const alvo = semAcento(adFatia.d[it[DESC]] + " " + it[CATMAT]);
      if (!termos.every(t => alvo.includes(t))) return false;
    }
    return true;
  });
}

const CHAVES = {
  valor: it => it[VALOR] ?? Infinity,
  desc: it => semAcento(adFatia.d[it[DESC]]),
  uasg: it => adFatia.u[it[UNI]][1],
  ata: it => it[ATA] + it[ITEM],
  fornecedor: it => adFatia.f[it[FORN]][1],
  registrada: it => it[QTDREG] ?? 0,
  adesao: it => it[MAXADESAO] ?? 0,
  // Saldo desconhecido vai para o fim — não é zero.
  saldo: it => it[SALDO] == null ? -1 : it[SALDO],
  dias: it => it[DIAS] ?? 0,
};

function desenharAdesao() {
  adLinhas = filtrarAdesao();
  const chave = CHAVES[adOrdem.campo];
  adLinhas.sort((a, b) => {
    const x = chave(a), y = chave(b);
    const r = (typeof x === "string") ? x.localeCompare(y, "pt-BR") : (x - y);
    return adOrdem.desc ? -r : r;
  });

  const confirmados = adLinhas.filter(it => it[SALDO] != null).length;
  $("#ad-resumo").innerHTML =
    `<b>${num(adLinhas.length)}</b> de ${num(adFatia.itens.length)} itens em ` +
    `“${escaparHtml(adFatia.nome)}” · ${num(confirmados)} com saldo confirmado` +
    (adLinhas.length > 400 ? ` · <span style="color:var(--alerta)">mostrando os 400 primeiros</span>` : "");

  $("#ad-corpo").innerHTML = adLinhas.slice(0, 400).map((it, i) => {
    const uni = adFatia.u[it[UNI]], forn = adFatia.f[it[FORN]];
    const saldo = it[SALDO] == null
      ? `<span class="etiqueta et-na" title="Não verificado — confirme no Contratos.gov.br">não verificado</span>`
      : (it[ACEITA] === false ? `<span class="etiqueta et-na">não aceita</span>`
                              : `<span class="etiqueta et-ok">${num(it[SALDO])}</span>`);
    const curto = (it[DIAS] ?? 999) < 60 ? ' class="et-curto"' : '';
    return `<tr>
      <td class="num">${moeda(it[VALOR])}</td>
      <td>${escaparHtml(adFatia.d[it[DESC]])}<br><span class="menor">CATMAT ${it[CATMAT]}</span></td>
      <td>${escaparHtml(uni[1])}<br><span class="menor">UASG ${escaparHtml(uni[0])}</span></td>
      <td>${escaparHtml(it[ATA])}<br><span class="menor">item ${it[ITEM]} · ${
        escaparHtml(it[MODAL] || "")} ${escaparHtml(it[COMPRA] || "")}</span></td>
      <td>${escaparHtml(forn[1])}<br><span class="menor">${cnpjFormatado(forn[0])}</span></td>
      <td class="num">${num(it[QTDREG])}</td>
      <td class="num">${it[MAXADESAO] > 0 ? num(it[MAXADESAO])
        : `<span class="etiqueta et-na" title="A ata não admite adesão">não permite</span>`}</td>
      <td class="num">${saldo}</td>
      <td class="num"><span${curto}>${it[DIAS]} dias</span><br>
          <span class="menor">${dia(it[VIGFIM])}</span></td>
      <td class="num">
        <button class="acao" data-linha="${i}" title="Ver os dados para preencher a solicitação">Usar</button>
        ${it[LINK] ? `<br><a href="${escaparHtml(it[LINK])}" target="_blank" rel="noopener" class="menor">PNCP</a>` : ""}
      </td>
    </tr>`;
  }).join("");

  $("#ad-vazio").hidden = adLinhas.length > 0;
  $$("th[data-ordem]").forEach(th => th.setAttribute("aria-sort",
    th.dataset.ordem === adOrdem.campo
      ? (adOrdem.desc ? "descending" : "ascending") : "none"));
}

function iniciarAdesao(trocarAba) {
  adAbrirRaiox = cnpj => { trocarAba("raiox"); consultarRaiox(cnpj); };

  document.addEventListener("aba:ativa", e => {
    if (e.detail === "adesao") carregarIndiceAdesao().then(ok => ok && sugerirAdesao());
  });
  if (!$("#painel-adesao").hidden) carregarIndiceAdesao();

  $("#ad-q").addEventListener("input", sugerirAdesao);
  $("#ad-q").addEventListener("keydown", e => {
    const itens = $$("#ad-sugestoes li[data-pdm], #ad-sugestoes li[data-cnpj]");
    if (!itens.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      adMarcado = (adMarcado + (e.key === "ArrowDown" ? 1 : -1) + itens.length) % itens.length;
      itens.forEach((li, i) => li.setAttribute("aria-selected", i === adMarcado));
      itens[adMarcado].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault(); (itens[adMarcado] || itens[0]).click();
    } else if (e.key === "Escape") { $("#ad-sugestoes").hidden = true; }
  });
  $("#ad-sugestoes").addEventListener("click", e => {
    const li = e.target.closest("li[data-pdm], li[data-cnpj]");
    if (!li) return;
    if (li.dataset.cnpj) abrirFornecedor(li.dataset.cnpj);
    else abrirPdm(li.dataset.pdm, li.querySelector(".nome").textContent);
  });
  document.addEventListener("click", e => {
    if (!e.target.closest("#painel-adesao .busca")) $("#ad-sugestoes").hidden = true;
  });

  ["#ad-filtro", "#ad-uasg", "#ad-fornecedor", "#ad-dias", "#ad-so-saldo",
   "#ad-incluir-vedados"].forEach(s =>
    $(s).addEventListener("input", () => adFatia && desenharAdesao()));

  $$("#painel-adesao th[data-ordem]").forEach(th =>
    th.addEventListener("click", () => {
      const campo = th.dataset.ordem;
      adOrdem = { campo, desc: adOrdem.campo === campo ? !adOrdem.desc : campo !== "valor" };
      desenharAdesao();
    }));

  $("#ad-corpo").addEventListener("click", e => {
    const b = e.target.closest("button[data-linha]");
    if (!b) return;
    abrirDialogoItem(adLinhas[+b.dataset.linha]);
  });
}

function abrirDialogoItem(it) {
  const uni = adFatia.u[it[UNI]], forn = adFatia.f[it[FORN]];
  const campos = [
    ["Unidade gerenciadora", `${uni[0]} — ${uni[1]}`],
    ["Número da compra/Ano", it[COMPRA] || "— (a API não informou)"],
    ["Modalidade da compra", it[MODAL] || "—"],
    ["Número da ata/Ano", it[ATA]],
    ["Fornecedor", `${cnpjFormatado(forn[0])} — ${forn[1]}`],
    ["Item da ata", it[ITEM]],
    ["CATMAT", String(it[CATMAT])],
    ["Valor unitário", moeda(it[VALOR])],
    ["Qtd registrada", num(it[QTDREG])],
  ];
  // Com limite zero não há adesão a pedir: mostrar "50% do registrado" ali
  // sugeriria uma quantidade que o sistema vai recusar.
  if (it[MAXADESAO] > 0) {
    campos.push(["Limite de adesão (2× registrado)", num(it[MAXADESAO])],
                ["Saldo de adesão", it[SALDO] == null ? "não verificado" : num(it[SALDO])],
                ["Máx. por órgão (50% do registrado)", num((it[QTDREG] || 0) / 2)]);
  } else {
    campos.push(["Adesão", "não permitida nesta ata (limite zero)"]);
  }
  campos.push(["Vigência até", `${dia(it[VIGFIM])} (${it[DIAS]} dias)`]);

  $("#dlg-titulo").textContent = "Dados para a tela “Solicitar adesão”";
  $("#dlg-campos").innerHTML = campos.map(([k, v]) =>
    `<div class="campo"><span>${escaparHtml(k)}</span><b>${escaparHtml(v)}</b></div>`).join("");

  const bRaiox = $("#dlg-raiox");
  bRaiox.hidden = false;
  bRaiox.onclick = () => { $("#dlg").close(); adAbrirRaiox(forn[0]); };

  $("#dlg-copiar").onclick = async () => {
    try {
      await navigator.clipboard.writeText(campos.map(([k, v]) => `${k}: ${v}`).join("\n"));
      $("#dlg-copiar").textContent = "Copiado ✓";
    } catch { $("#dlg-copiar").textContent = "Não consegui copiar"; }
    setTimeout(() => $("#dlg-copiar").textContent = "Copiar tudo", 1800);
  };
  $("#dlg").showModal();
}
