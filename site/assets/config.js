// Único ponto de configuração do site.
window.CONFIG = {
  // URL base da API do Raio-X hospedada no Render, SEM barra no fim.
  // Exemplo: "https://raiox-fornecedor.onrender.com"
  // Enquanto estiver vazia, a aba Raio-X explica o que falta em vez de quebrar.
  RAIOX_API: "https://raiox-fornecedor-api.onrender.com",

  // Busca do PNCP. As duas APIs mandam Access-Control-Allow-Origin: *, então o
  // navegador chama direto -- por isso esta aba não tem dado pré-gerado.
  PNCP_BUSCA: "https://pncp.gov.br/api/search/",

  // A API do PNCP derruba conexões em rajada (medido: requisições seguidas
  // voltaram vazias). Daí o atraso ao digitar e uma única repetição.
  DEBOUNCE_MS: 500,
  TENTATIVAS: 2,
};
