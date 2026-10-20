# Crons de cobrança (Railway Cron)

Cada cron é um serviço Railway do mesmo repositório, com `startCommand` e
`cronSchedule` próprios. Os horários do Railway são **UTC**.

| Serviço | Agenda (UTC) | Start command |
|---|---|---|
| `fitlog-cron-billing-carencias` | `0 * * * *` (a cada hora) | `flask billing-expirar-carencias` |
| `fitlog-cron-billing-tiers` | `0 6 * * *` (diário, 03:00 BRT) | `flask billing-rotina-diaria` |

## O que cada comando faz

**`billing-expirar-carencias`** (horário), etapas isoladas:
1. `expirar_pix_vencidos` — Pix ativo com `periodo_atual_fim` vencido → `past_due` + carência.
2. `expirar_carencias_vencidas` — `past_due` com carência esgotada → `blocked`.
3. `finalizar_cancelamentos_agendados` — cancelamento pedido e período pago acabado → `canceled`.

**`billing-rotina-diaria`** (diário), etapas isoladas:
1. `verificar_mudancas_tier_professores` — só auditoria (log `tier_pendente ...`).
2. `notificar_professores_tier_desatualizado` — aviso de upgrade (a cada 7 dias).
3. `notificar_vencimentos_pendentes` — régua de aviso de plano vencido.

Se qualquer etapa levantar exceção, as demais ainda rodam, a exceção vai para o
log e o Sentry e o comando termina com **código 1** (o Railway mostra a execução
como falha). Antes, o `sh -c "a; b; c"` só refletia o código do último comando.

## Modo grátis (`cobranca_ativa = False`)

Com a cobrança desligada em `/admin/telas-controladas`, os jobs 1, 2 (horário) e
1–3 (diário) **não fazem nada**: ninguém recebe "faça upgrade"/"plano expirou" e
nenhuma carência avança. `finalizar_cancelamentos_agendados` continua rodando
(é decisão do próprio usuário). Ao religar a cobrança, os jobs voltam sozinhos;
Pix vencidos entram em carência normal a partir daquele momento.

### Virada do modo grátis para cobrança

O trial (30 dias) expira por leitura, sem job. Quem se cadastrou durante o modo
grátis chegaria à virada com o trial já vencido. **Antes de religar a cobrança**:

```
railway run flask billing-reiniciar-trials                 # simulação (dry-run)
railway run flask billing-reiniciar-trials --executar --dias 30
```

Só afeta `trialing` com trial vencendo antes de `agora + dias`; nunca encurta um
trial mais longo.

## Corrida com o webhook

Os jobs mudam o status por `UPDATE ... WHERE id = :id AND <condição original>`
(`BillingService._transicionar`). Se o webhook confirmar o pagamento entre o
SELECT do job e a escrita, a condição deixa de casar e a assinatura permanece
`active` — o job nunca sobrescreve um pagamento recém-confirmado.

## Régua de vencimento

Marcos em dias de atraso: 1, 2, 3, 6, 9, 12, 15, 18 e depois a cada 10 dias.
`ultima_notificacao_vencimento_dias` guarda o **marco** já avisado; se o cron
perder o dia exato de um marco, o aviso sai no run seguinte (uma vez só).

## Sugestão operacional (builds)

Todos os crons rebuildam a cada push. Limite com `watchPatterns` por serviço, por
exemplo: `services/**`, `models.py`, `app.py`, `utils/**`, `requirements.txt`.
