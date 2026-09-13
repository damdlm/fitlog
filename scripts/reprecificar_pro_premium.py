#!/usr/bin/env python3
"""Atualiza no Asaas o valor cobrado das assinaturas de cartão JÁ
ATIVAS do Plano Pró/Premium, para refletir a reprecificação (Pró
R$29,90 -> R$10,90, Premium R$99,90 -> R$29,90 -- ver migration
a2b3c4d5e6f7_reprecifica_pro_e_premium).

A migration de banco só corrige o preço de TABELA (usado em cobranças
novas a partir de agora). Quem já tem uma assinatura recorrente ativa
no Asaas continua sendo cobrado pelo valor antigo até alguém chamar
PUT /subscriptions/{id} com o valor novo -- é exatamente o que este
script faz, um usuário de cada vez, via
BillingService.atualizar_valor_assinatura (mesma função usada pelo
fluxo normal de upgrade/downgrade de faixa).

Só afeta assinaturas com forma_pagamento='cartao' -- quem paga via
Pix não tem assinatura recorrente no gateway; o próximo Pix confirmado
já vai usar o preco_centavos novo automaticamente (calculado na hora,
ver BillingService.criar_pagamento_pix_ativacao), sem precisar de
nenhuma ação aqui.

USO:
    python scripts/reprecificar_pro_premium.py --dry-run   # só lista, não altera nada
    python scripts/reprecificar_pro_premium.py --confirm   # aplica de verdade

Rodar DEPOIS que a migration a2b3c4d5e6f7 já tiver sido aplicada
(senão Plano.preco_centavos ainda estaria no valor antigo, e o script
"atualizaria" a assinatura pro mesmo valor que já está).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import Assinatura, Plano  # noqa: E402
from services.billing_service import BillingService  # noqa: E402

CODIGOS_AFETADOS = ('professor_pro', 'professor_premium')


def main():
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--dry-run', action='store_true', help='Só lista quem seria afetado, não chama o Asaas')
    grupo.add_argument('--confirm', action='store_true', help='Aplica de verdade (chama o Asaas)')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        planos = {p.codigo: p for p in Plano.query.filter(Plano.codigo.in_(CODIGOS_AFETADOS)).all()}
        for codigo in CODIGOS_AFETADOS:
            plano = planos.get(codigo)
            if plano:
                print(f'{codigo}: preço de tabela atual = R${plano.preco_centavos / 100:.2f}')

        assinaturas = (
            Assinatura.query
            .join(Plano, Assinatura.plano_id == Plano.id)
            .filter(
                Plano.codigo.in_(CODIGOS_AFETADOS),
                Assinatura.status == 'active',
                Assinatura.forma_pagamento == 'cartao',
                Assinatura.gateway_subscription_id.isnot(None),
            )
            .all()
        )

        print(f'\n{len(assinaturas)} assinatura(s) de cartão ativa(s) em Pró/Premium encontrada(s).\n')

        sucesso = 0
        falha = 0
        for assinatura in assinaturas:
            plano = assinatura.plano
            usuario = assinatura.usuario
            rotulo = f'usuario_id={assinatura.usuario_id} ({usuario.username if usuario else "?"}) plano={plano.codigo} novo_valor=R${plano.preco_centavos / 100:.2f}'

            if args.dry_run:
                print(f'[dry-run] atualizaria: {rotulo}')
                continue

            try:
                BillingService.atualizar_valor_assinatura(assinatura, plano)
                print(f'[ok] {rotulo}')
                sucesso += 1
            except Exception as exc:
                print(f'[ERRO] {rotulo} -- {exc}')
                falha += 1
            time.sleep(0.3)  # evita rajada contra a API do Asaas

        if args.confirm:
            print(f'\nConcluído: {sucesso} atualizada(s), {falha} com erro.')


if __name__ == '__main__':
    main()