"use strict";
// Aba Raio-X — consulta ao vivo na API hospedada no Render.
//
// GET {RAIOX_API}/api/raiox/{cnpj} devolve:
//   { cnpj, gerado_em, versao_regras, cobertura,
//     resultados: [{ fonte, rotulo, estado, consultado_em, url, achados:[...] }],
//     avaliacao: { parecer, pontos, cobertura, justificativa, versao_regras } }
//
// A regra que a tela existe para preservar: o dossiê distingue "consultei e nada
// consta" de "não consegui consultar". Reduzir os cinco estados a verde/vermelho
// destruiria exatamente a garantia que dá valor ao relatório.

const ESTADOS = {
  OK_SEM_ACHADO:     { classe: "et-ok",   texto: "consultado — nada consta", conclusivo: true },
  OK_COM_ACHADO:     { classe: "et-ruim", texto: "achado encontrado",        conclusivo: true },
  INDISPONIVEL:      { classe: "et-na",   texto: "NÃO CONSULTADO — fonte indisponível" },
  SEM_CREDENCIAL:    { classe: "et-na",   texto: "NÃO CONSULTADO — falta credencial" },
  NAO_AUTOMATIZAVEL: { classe: "et-na",   texto: "NÃO CONSULTADO — exige ação humana" },
};

const PARECERES = {
  IMPEDITIVO:   { classe: "et-ruim", texto: "Impeditivo — não contrate sem decisão de alçada superior" },
  RISCO_ALTO:   { classe: "et-ruim", texto: "Risco alto" },
  RISCO_MEDIO:  { classe: "et-na",   texto: "Risco médio" },
  RISCO_BAIXO:  { classe: "et-ok",   texto: "Risco baixo" },
  INCONCLUSIVO: { classe: "et-na",   texto: "Inconclusivo — não foi consultado o bastante para opinar" },
};

const GRAVIDADES = { VETO: "et-ruim", ALTA: "et-ruim", MEDIA: "et-na", BAIXA: "et-na" };

function apiConfigurada() {
  return !!(window.CONFIG && CONFIG.RAIOX_API);
}

// `justificativa` vem como LISTA de frases (a segunda costuma ser a ressalva
// sobre as fontes que nao responderam) -- concatenar viraria uma linha so.
function justificativaHtml(j) {
  if (!j) return "";
  const linhas = Array.isArray(j) ? j : [j];
  return `<br>` + linhas.map(t =>
    `<span class="menor">${escaparHtml(t)}</span>`).join("<br>");
}

function desenharRaiox(d) {
  const aval = d.avaliacao || {};
  const p = PARECERES[aval.parecer] || { classe: "et-na", texto: aval.parecer || "—" };
  const cobertura = Math.round((aval.cobertura ?? d.cobertura ?? 0) * 100);
  const resultados = d.resultados || [];
  const naoConsultadas = resultados.filter(r => !ESTADOS[r.estado]?.conclusivo);
  const achados = resultados.flatMap(r => (r.achados || []).map(a => ({ ...a, rotulo: r.rotulo })));

  const razao = (resultados.find(r => r.fonte === "receita_federal")
    || {}).dados?.razao_social;

  // A cobertura vem ANTES do parecer, de propósito: é a ressalva que qualifica
  // tudo o que vem depois.
  const avisoCobertura = naoConsultadas.length
    ? `<div class="aviso aviso-alerta">
         <b>${naoConsultadas.length} fonte(s) não foram consultadas</b> —
         cobertura de ${cobertura}% das fontes automatizáveis. O que não foi
         consultado não vira “nada consta”.
       </div>`
    : `<div class="aviso aviso-info">Todas as fontes automatizáveis responderam
        (cobertura ${cobertura}%).</div>`;

  const listaAchados = achados.length
    ? `<div class="tabela" style="margin-bottom:16px"><table>
         <thead><tr><th>Achado</th><th>Gravidade</th><th>Fonte</th><th>Detalhe</th></tr></thead>
         <tbody>${achados.map(a => `<tr>
           <td><b>${escaparHtml(a.titulo)}</b></td>
           <td><span class="etiqueta ${GRAVIDADES[a.gravidade] || "et-na"}">${escaparHtml(a.gravidade)}</span></td>
           <td>${escaparHtml(a.rotulo || a.fonte || "")}</td>
           <td>${escaparHtml(a.detalhe || "")}</td>
         </tr>`).join("")}</tbody></table></div>`
    : `<p class="dica" style="margin-bottom:16px">Nenhum achado nas fontes que responderam.</p>`;

  const tabelaFontes = `<div class="tabela"><table>
      <thead><tr><th>Fonte</th><th>Estado</th><th>Consultada em</th><th>Achados</th></tr></thead>
      <tbody>${resultados.map(r => {
        const e = ESTADOS[r.estado] || { classe: "et-na", texto: r.estado };
        return `<tr>
          <td>${escaparHtml(r.rotulo || r.fonte)}
            ${r.url ? `<br><a class="menor" href="${escaparHtml(r.url)}" target="_blank" rel="noopener">origem</a>` : ""}</td>
          <td><span class="etiqueta ${e.classe}">${escaparHtml(e.texto)}</span></td>
          <td class="menor">${r.consultado_em ? new Date(r.consultado_em).toLocaleString("pt-BR") : "—"}</td>
          <td class="num">${(r.achados || []).length || "—"}</td>
        </tr>`;
      }).join("")}</tbody></table></div>`;

  $("#rx-resultado").hidden = false;
  $("#rx-resultado").innerHTML = `
    <h2 style="font-size:16px;margin:4px 0 2px">${escaparHtml(razao || cnpjFormatado(d.cnpj))}</h2>
    <p class="menor" style="margin:0 0 12px">CNPJ ${cnpjFormatado(d.cnpj)} ·
       consultado em ${d.gerado_em ? new Date(d.gerado_em).toLocaleString("pt-BR") : "agora"}
       · regras ${escaparHtml(d.versao_regras || "—")}</p>
    ${avisoCobertura}
    <p style="margin:0 0 14px"><span class="etiqueta ${p.classe}" style="font-size:13px;padding:4px 12px">
       ${escaparHtml(p.texto)}</span>
       ${justificativaHtml(aval.justificativa)}</p>
    <h3 style="font-size:14px;margin:18px 0 8px">Achados</h3>
    ${listaAchados}
    <h3 style="font-size:14px;margin:18px 0 8px">Fontes consultadas</h3>
    ${tabelaFontes}`;
}

async function consultarRaiox(cnpjBruto) {
  const digitos = String(cnpjBruto || $("#rx-cnpj").value).replace(/\D/g, "");
  $("#rx-cnpj").value = cnpjFormatado(digitos) || cnpjBruto || "";
  limparErro("#erro-raiox");

  if (digitos.length !== 14) {
    mostrarErro("#erro-raiox", "CNPJ inválido.", "São 14 dígitos.");
    return;
  }
  if (!apiConfigurada()) {
    mostrarErro("#erro-raiox", "A API do Raio-X ainda não foi configurada.",
      "Preencha RAIOX_API em site/assets/config.js com a URL do serviço no Render.");
    return;
  }

  // Medido contra o serviço: ~22 s só para o Render acordar, mais ~78 s de
  // coleta (as fontes são consultadas em sequência, de propósito). Passar disso
  // sem dizer nada faria a pessoa achar que travou.
  $("#rx-resultado").hidden = false;
  const inicio = Date.now();
  $("#rx-resultado").innerHTML =
    `<p class="dica"><span class="carregando"></span>
     Consultando as bases públicas, uma a uma — costuma levar cerca de um minuto,
     e mais um pouco se for a primeira consulta do dia.
     <b id="rx-cronometro">0s</b></p>`;
  const cronometro = setInterval(() => {
    const el = document.getElementById("rx-cronometro");
    if (el) el.textContent = Math.round((Date.now() - inicio) / 1000) + "s";
  }, 1000);

  try {
    const d = await buscarJson(`${CONFIG.RAIOX_API}/api/raiox/${digitos}`,
                               { tentativas: 1, timeoutMs: 240000 });
    desenharRaiox(d);
  } catch (e) {
    $("#rx-resultado").hidden = true;
    mostrarErro("#erro-raiox",
      "Não consegui consultar o Raio-X — isto não é um parecer sobre a empresa.",
      `O serviço pode estar acordando ou fora do ar. Tente de novo. (${e.message})`);
  } finally {
    clearInterval(cronometro);
  }
}

function iniciarRaiox() {
  if (!apiConfigurada()) {
    $("#rx-dica").innerHTML =
      `<span class="etiqueta et-na">não configurado</span> Preencha
       <code>RAIOX_API</code> em <code>site/assets/config.js</code> com a URL do
       serviço no Render (sem barra no fim) e a aba passa a funcionar.`;
  }
  $("#rx-consultar").addEventListener("click", () => consultarRaiox());
  $("#rx-cnpj").addEventListener("keydown", e => {
    if (e.key === "Enter") consultarRaiox();
  });
  $("#rx-cnpj").addEventListener("blur", () => {
    const d = $("#rx-cnpj").value.replace(/\D/g, "");
    if (d.length === 14) $("#rx-cnpj").value = cnpjFormatado(d);
  });
}
