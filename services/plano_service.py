"""Serviço para o admin editar o preço dos planos direto na tela
/admin/telas-controladas -- sem precisar de deploy/migration pra cada
ajuste de valor (ver models.py:Plano, cujo docstring já previa esse
uso: "Ficam no banco... para permitir ajustar preço... sem precisar
de deploy")."""

import re
from dataclasses import dataclass, field

from models import db, Plano

# Ordem de exibição na tela do admin -- Fit -> Pró -> Premium, não a
# ordem alfabética do nome nem a de criação no banco.
CODIGOS_EDITAVEIS = ('aluno_fit', 'professor_pro', 'professor_premium')


@dataclass
class ResultadoAtualizacaoPrecos:
    erros: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros


class PlanoService:

    @staticmethod
    def listar_editaveis() -> list[Plano]:
        """Os 3 planos que aparecem na tela do admin pra editar preço,
        na ordem CODIGOS_EDITAVEIS. Um código que não existir no banco
        é simplesmente pulado (não derruba a tela)."""
        planos = {p.codigo: p for p in Plano.query.filter(Plano.codigo.in_(CODIGOS_EDITAVEIS)).all()}
        return [planos[codigo] for codigo in CODIGOS_EDITAVEIS if codigo in planos]

    @staticmethod
    def _parse_valor_para_centavos(valor_str: str) -> int | None:
        """Aceita "10,90" (formato brasileiro, caso alguém digite ou
        cole assim) e "10.90" (o que o <input type=number> do HTML
        manda) -- normaliza vírgula pra ponto antes de converter.
        Retorna None se o texto não for um valor válido (vazio, texto
        não numérico, mais de 2 casas decimais)."""
        if not valor_str:
            return None
        limpo = valor_str.strip().replace(',', '.')
        if not re.fullmatch(r'\d+(\.\d{1,2})?', limpo):
            return None
        return round(float(limpo) * 100)

    @staticmethod
    def atualizar_precos(form) -> ResultadoAtualizacaoPrecos:
        """Lê preco_<codigo> de cada plano editável no form (ver
        template admin/telas_controladas.html), valida e salva.

        Tudo-ou-nada: se QUALQUER valor vier inválido (vazio, texto,
        zero ou negativo), nada é salvo -- evita persistir 2 de 3
        planos e deixar o formulário num estado parcial confuso pro
        admin. Quem chama decide o que fazer com resultado.erros
        (normalmente: mostrar via flash e não redirecionar como
        sucesso).

        NÃO mexe em assinaturas já ativas no Asaas -- só corrige o
        preço de TABELA, usado em cobranças novas a partir de agora
        (checkout novo, upgrade/downgrade de faixa, próximo Pix
        avulso). Pra reajustar quem já é assinante de cartão de um
        plano cujo preço mudou, é preciso chamar
        BillingService.atualizar_valor_assinatura pra cada assinatura
        ativa afetada -- ver scripts/reprecificar_pro_premium.py como
        exemplo desse tipo de script (não é acionado automaticamente
        por este serviço)."""
        resultado = ResultadoAtualizacaoPrecos()
        planos = PlanoService.listar_editaveis()
        novos_valores = {}

        for plano in planos:
            valor_str = form.get(f'preco_{plano.codigo}')
            centavos = PlanoService._parse_valor_para_centavos(valor_str)
            if centavos is None or centavos <= 0:
                resultado.erros.append(f'Valor inválido para {plano.nome}: "{valor_str}".')
                continue
            novos_valores[plano.id] = centavos

        if not resultado.ok:
            return resultado

        for plano in planos:
            plano.preco_centavos = novos_valores[plano.id]
        db.session.commit()
        return resultado
