# Screenshots do PWA (Rich Install UI)

Esta pasta foi preparada para receber capturas de tela reais do FitLog,
usadas pelo `manifest.json` para exibir uma prévia do app na hora da
instalação (recurso do Chrome/Edge no Android e Desktop).

Nenhum screenshot foi adicionado ainda porque não existiam imagens reais
no projeto — o `manifest.json` **não foi alterado** para não referenciar
arquivos inexistentes (isso quebraria a validação do manifest em alguns
navegadores).

## O que precisa ser adicionado

1. Uma captura em formato "wide" (área de trabalho), ex: `home.png` —
   recomendado 1280x720.
2. Uma captura em formato "narrow" (celular), ex: `mobile.png` —
   recomendado 390x844 (ou a resolução real do dispositivo usado).

Depois de adicionar os arquivos aqui, inclua no `static/manifest.json`:

```json
"screenshots": [
  {
    "src": "/static/screenshots/home.png",
    "sizes": "1280x720",
    "type": "image/png",
    "form_factor": "wide",
    "label": "Dashboard do FitLog"
  },
  {
    "src": "/static/screenshots/mobile.png",
    "sizes": "390x844",
    "type": "image/png",
    "form_factor": "narrow",
    "label": "Acompanhe seus treinos"
  }
]
```
