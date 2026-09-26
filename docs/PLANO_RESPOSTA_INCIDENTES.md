# Plano de Resposta a Incidentes de Segurança — FitLog

Documento interno. Descreve os passos a seguir caso ocorra um incidente de
segurança envolvendo dados pessoais (vazamento, acesso indevido, perda de
dados). Não inventa prazos legais específicos onde a lei não os fixa — ver
observação sobre a LGPD no final.

## 1. Identificação
Qualquer sinal de incidente (alerta do Sentry, comportamento anômalo no banco,
aviso de um usuário, aviso de um fornecedor como Railway ou Asaas) deve ser
levado a sério e investigado, mesmo que pareça pequeno no início.

## 2. Classificação
Avaliar rapidamente:
- Houve exposição de dados pessoais? De quais categorias (básicos, sensíveis,
  financeiros)?
- Quantos titulares foram potencialmente afetados?
- O incidente ainda está em andamento ou já foi contido?

## 3. Contenção
Agir imediatamente para estancar o problema: revogar credenciais comprometidas,
desabilitar a funcionalidade afetada, bloquear o vetor de acesso indevido — o
que for aplicável ao caso.

## 4. Preservação de evidências
Antes de "limpar" qualquer coisa, guardar logs, capturas de tela e registros
relevantes do incidente — são necessários tanto para investigar a causa raiz
quanto para eventual comunicação à ANPD/aos titulares.

## 5. Avaliação de risco
Determinar se o incidente pode acarretar risco ou dano relevante aos titulares
(Art. 48 da LGPD) — esse julgamento, em casos de dúvida, deve envolver
orientação jurídica antes de decidir se há dever de comunicação.

## 6. Identificação dos titulares afetados
Levantar exatamente quais contas/registros foram impactados, evitando
notificar mais (ou menos) pessoas do que o necessário.

## 7. Análise da obrigação de comunicação
A LGPD (Art. 48) exige comunicação à ANPD e ao titular em caso de incidente que
possa acarretar risco ou dano relevante, "em prazo razoável" — **a lei não fixa
um número de dias específico como outras legislações (ex.: GDPR fixa 72h); o
prazo razoável e a forma exata de comunicação devem ser definidos com apoio
jurídico no momento do incidente**, considerando a gravidade e a regulamentação
da ANPD vigente à época.

## 8. Comunicação à ANPD (quando aplicável)
Feita conforme o canal oficial vigente da ANPD no momento do incidente — não
documentamos aqui um canal fixo, pois isso pode mudar; consultar
gov.br/anpd no momento do incidente.

## 9. Comunicação aos titulares (quando aplicável)
Direta (e-mail cadastrado) sempre que viável, com linguagem clara sobre o que
aconteceu, quais dados foram afetados e o que a pessoa pode fazer a respeito
(ex.: trocar senha).

## 10. Correção
Implementar a correção técnica definitiva da causa raiz — não só a contenção
temporária do passo 3.

## 11. Documentação
Registrar o incidente (o que aconteceu, quando, como foi tratado, o que foi
corrigido) em um registro interno, mesmo quando não houver dever de comunicar
externamente — serve como histórico e para demonstrar boas práticas de
governança se questionado no futuro.

## 12. Pós-incidente
Revisar o que permitiu o incidente acontecer e se algum controle adicional
(técnico ou de processo) deveria ser adotado para reduzir a chance de
recorrência.

---

**Nota importante**: este plano descreve o processo, não substitui orientação
jurídica no momento de um incidente real — principalmente nos passos 5, 7 e 8,
onde a decisão sobre comunicar ou não, e como, tem consequência legal direta.