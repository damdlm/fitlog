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
