# Política de Retenção de Dados — FitLog

Documento interno. Descreve por quanto tempo cada categoria de dado é
mantida e o que acontece com ela depois disso. Não implementa nenhum
job de expiração automática — é só a documentação do que a aplicação
já faz hoje (ver `services/privacidade_service.py`) e do que ainda
depende de decisão jurídica/de negócio.

| Categoria de dado | Onde vive | Retenção | Destino após o prazo | Justificativa |
|---|---|---|---|---|
| Conta (nome, e-mail, telefone, username) | `User` | Enquanto a conta estiver ativa | Exclusão/anonimização a pedido do titular (`PrivacidadeService.anonimizar_conta`) | Execução do contrato — só precisamos do dado enquanto a conta existe |
| Dados de treino (versões, exercícios, cargas, repetições) | `VersaoGlobal`, `TreinoVersao`, `RegistroTreino`, `HistoricoTreino`, `ExercicioUsuario` | Enquanto a conta estiver ativa | **Excluído** (DELETE físico) na exclusão/anonimização da conta — não fica retido nem "anonimizado": continuava vinculado ao mesmo `user_id`, então mantê-lo seria pseudonimização, não anonimização, e não há finalidade legítima documentada para retê-lo depois que a conta é excluída. O professor vinculado deixa de conseguir acessar esse histórico (o vínculo já é desativado antes disso, ver linha abaixo) | Sem finalidade legítima de retenção após a exclusão — as únicas métricas agregadas que dependem de contas ativas (ex.: ranking) já filtram por `User.ativo`, não pelo histórico individual |
| Vínculo aluno-professor (`AlunoProfessor`, `SolicitacaoVinculo`) | tabelas próprias | Enquanto o vínculo estiver ativo | Desativado (`ativo=False` / `status='cancelado'`) na anonimização da conta de qualquer um dos dois lados | Execução do contrato — só existe enquanto os dois lados consentirem no vínculo |
| Consentimentos e aceites LGPD (`ConsentimentoLGPD`) | tabela própria | Permanente (nunca é apagado, nem na anonimização da conta) | Retenção controlada, sem prazo de expiração. Continua vinculado ao `usuario_id` (pseudonimizado, não anônimo) — mas sem os dados pessoais do `User` (já removidos na mesma operação), esse vínculo sozinho não permite reidentificar o titular | É a própria prova de que houve consentimento/aceite — apagar destruiria a evidência que a LGPD pede para poder comprovar |
| Tokens de redefinição de senha (`PasswordResetToken`) | tabela própria | Curtíssimo prazo (expira em minutos, ver `User.get_reset_token`); invalidado antes disso se a conta for excluída | Eliminação (registro marcado como usado, nunca mais aceito) | Não há motivo para guardar depois de usado/expirado |
| Dados de cobrança/assinatura (`Assinatura`, `EventoWebhookAsaas`) | tabelas próprias | Conforme obrigação legal aplicável | Retenção controlada / eliminação-anonimização quando a obrigação deixar de existir | Obrigação legal/contratual (fiscal e de defesa em eventual disputa de cobrança) — **prazo exato pendente de validação jurídica/contábil, não estimado aqui** |
| Conteúdo trocado com o FitBot | Não persistido em banco — só existe na memória da requisição e no provedor de IA externo (Groq/Gemini/OpenAI) durante o processamento | N/A (não armazenamos) | — | Minimização: o FitLog não guarda histórico de conversas do FitBot |
| Logs de aplicação/segurança | Infraestrutura de log da Railway | Conforme período padrão da plataforma de hospedagem | Eliminação automática pela plataforma | Diagnóstico de incidentes de segurança — **prazo exato depende da configuração da Railway, não estimado aqui** |
| Solicitações de titular (exportação/exclusão) | `ConsentimentoLGPD` (tipo `exclusao_conta`) | Permanente, junto com os demais consentimentos | Retenção controlada | Comprovação de que o pedido foi atendido |

## Observações

- Nenhum prazo legal foi inventado neste documento. Onde a retenção
  depende de uma obrigação legal específica (dados fiscais/de
  cobrança, logs de infraestrutura), isso está marcado explicitamente
  como pendente de validação, em vez de um número chutado.
- Este documento cobre o que existe hoje na aplicação. Se um novo tipo
  de dado for adicionado no futuro (nova tabela, nova integração),
  ele deveria ganhar uma linha aqui antes de ir para produção.
- Não há, neste momento, nenhum job automático de expiração/purga de
  dados — a política acima é aplicada pontualmente, através dos fluxos
  de autoatendimento já existentes (Central de Privacidade) e da
  invalidação de vínculos/tokens/histórico de treino/cache feita em
  `anonimizar_conta`.
- "Anonimizado" e "pseudonimizado" não são a mesma coisa, e este
  documento evita usar o primeiro termo quando o segundo é o que
  realmente acontece: um dado só é tratado como anonimizado aqui
  quando não sobra nenhum identificador (direto ou indireto) capaz de
  religá-lo ao titular. Um dado que continua preso a um `user_id` ou
  a qualquer outra chave que permita reencontrar o titular é
  pseudonimizado/desvinculado, mesmo que nome/e-mail/telefone tenham
  sido removidos — e só fica retido quando a linha correspondente
  nesta tabela documentar uma finalidade legítima para isso.