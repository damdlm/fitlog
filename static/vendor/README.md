# Bibliotecas de terceiros servidas localmente

Antes: Bootstrap CSS/JS e Bootstrap Icons vinham do CDN externo
`cdn.jsdelivr.net`. Trocamos por arquivos locais porque:

1. Cada domínio externo custa uma resolução DNS + handshake TLS extra
   na primeira visita.
2. Desde ~2020, Chrome/Firefox/Safari particionam o cache HTTP por site
   de origem — o benefício de "o usuário já tinha isso em cache de
   outro site que usa o mesmo CDN" não existe mais na prática.
3. Servindo do mesmo domínio, esses arquivos passam a se beneficiar do
   `Cache-Control`/gzip configurados para `/static/` na própria
   aplicação, e reaproveitam a conexão HTTP já aberta com o FitLog.

## Conteúdo e origem

- `bootstrap/` — Bootstrap **5.3.0**, `dist/css/bootstrap.min.css` e
  `dist/js/bootstrap.bundle.min.js` (+ `.map` correspondentes), extraídos
  do pacote npm `bootstrap@5.3.0` (mesma versão que estava fixada no CDN).
- `bootstrap-icons/` — Bootstrap Icons **1.11.3**, `font/bootstrap-icons.min.css`
  + `font/fonts/*` (woff2/woff), extraídos do pacote npm
  `bootstrap-icons@1.11.3`.

- `html-to-image/` — html-to-image **1.11.13** (MIT), `dist/html-to-image.js` + `LICENSE`,
  extraídos do pacote npm `html-to-image@1.11.13`. Usado só na versão embed
  da página pública do professor (`pagina_publica_embed.html`) para gerar a
  imagem 1080x1920 que o botão Compartilhar do modal envia.

- `driverjs/` — Driver.js **1.10.0** (MIT), `driver.js.iife.js` + `driver.css` + `LICENSE`,
  extraídos do pacote npm `driver.js@1.10.0` (pasta `dist/`). Usado no product tour da
  tela Registrar Treino (`static/js/registrar-treino-tour.js`). Global exposto:
  `window.driver.js.driver`.

- `chartjs/` — Chart.js **4.5.1** (MIT), `chart.umd.min.js` (+ `.map`) + `LICENSE`,
  do pacote npm `chart.js@4.5.1` (pasta `dist/`). Gráficos de Progresso, painel,
  calendário e telas do professor. Global: `window.Chart`.

- `fullcalendar/` — FullCalendar **5.11.3** (MIT), `main.min.js`, `main.min.css`,
  `locales/pt-br.js` + `LICENSE`, do pacote npm `fullcalendar@5.11.3`. Usado no
  calendário (`templates/calendar/calendario.html`). Global: `window.FullCalendar`.

- `html2canvas/` — html2canvas **1.4.1** (MIT), `html2canvas.min.js` + `LICENSE`,
  do pacote npm `html2canvas@1.4.1` (pasta `dist/`). Imagem de compartilhar do
  Registrar Treino.

- `sortablejs/` — SortableJS **1.15.7** (MIT), `Sortable.min.js` + `LICENSE`, do
  pacote npm `sortablejs@1.15.7`. Arrastar para reordenar exercícios nas telas de
  ficha (`cadastrar_treinos.html`, `ver_versao.html`).

- `musclemap/` — desenho do corpo do mapa muscular (tela Progresso):
  `corpo-fitlog.js` + `LICENSE` (MIT, © 2026 Melih Colpan). Caminhos SVG
  convertidos de MuscleMap (github.com/melihcolpan/MuscleMap, commit
  `d53ddf4`, `Sources/MuscleMap/Data/*Paths.swift`), só as regiões principais,
  já agrupadas nas regiões do FitLog. O aviso MIT vai no cabeçalho do arquivo.
  O estilo (silhueta, contorno, cores) é nosso, em
  `static/js/modules/mapa-muscular.js`. Global: `window.FitLogCorpo`.

Esses quatro vinham de `cdn.jsdelivr.net` (com reserva no `cdnjs`); os arquivos
daqui são byte a byte os mesmos (hash SHA-384 igual ao `integrity` que as
páginas usavam). Servidos localmente, deixam de falhar quando o CDN é bloqueado
ou lento na rede do aluno, e as páginas usam `static_v()` para trocar o cache a
cada deploy.

## Como atualizar a versão no futuro

```bash
npm pack bootstrap@<versao> bootstrap-icons@<versao>
# extrair o .tgz e copiar dist/css, dist/js (bootstrap) e
# font/bootstrap-icons.min.css + font/fonts (bootstrap-icons)
# para dentro das pastas correspondentes aqui, sobrescrevendo.
```

Não editar os arquivos `.min.css`/`.min.js` diretamente — são gerados,
qualquer mudança visual/comportamental deve ir em `static/css/`ou
`static/js/` próprios do projeto, carregados depois destes no `base.html`.