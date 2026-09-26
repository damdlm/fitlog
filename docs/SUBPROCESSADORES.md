# Subprocessadores — FitLog

Documento interno. Lista os terceiros que processam dados em nome do FitLog,
para consulta interna e para servir de base à seção "Com quem compartilhamos"
da Política de Privacidade. Segue o princípio de não inventar informação: onde
o dado não pôde ser confirmado a partir do código ou da documentação pública
do fornecedor, está marcado como tal.

| Fornecedor | Finalidade | Dados enviados | País/local confirmado | Transferência internacional | Retenção |
|---|---|---|---|---|---|
| **Asaas** | Gateway de pagamento (cobrança, assinaturas, emissão de NFS-e) | Nome, e-mail, CPF/CNPJ, telefone, endereço, dados da cobrança (valor, forma de pagamento) — nunca o número completo do cartão (o FitLog não tem acesso a isso, fica só com a Asaas/bandeira) | Brasil (empresa brasileira, CNPJ nacional) | **NÃO CONFIRMADO se há transferência internacional na infraestrutura interna da Asaas** — a empresa em si é nacional, o que é diferente de dizer que o processamento nunca toca servidor fora do Brasil | Conforme obrigação legal — ver `docs/POLITICA_RETENCAO_DADOS.md` (pendente de validação jurídica/contábil) |
| **Groq** | Provedor de IA para o FitBot (chat de texto) | Conteúdo da mensagem enviada ao FitBot, contexto da conversa | Empresa americana | Sim | Não persistido pelo FitLog; retenção do lado da Groq não confirmada |
| **Google (Gemini)** | Provedor de IA para o FitBot (texto e imagem) | Conteúdo da mensagem e, quando o usuário envia, a imagem anexada | Empresa americana/global | Sim | Não persistido pelo FitLog; retenção do lado do Google não confirmada |
| **OpenAI** | Provedor de IA para o FitBot (reserva automática, caso Groq/Gemini falhem) | Mesmo conteúdo enviado aos outros provedores de IA | Empresa americana | Sim | Não persistido pelo FitLog; retenção do lado da OpenAI não confirmada |
| **Resend** | Envio de e-mails transacionais (ex.: redefinição de senha) | E-mail do destinatário, conteúdo do e-mail enviado | Empresa americana | Sim | Não confirmada (depende da política do Resend) |
| **Railway** | Hospedagem da aplicação e do banco de dados | Todo o banco de dados do FitLog (é onde ele roda) | Confirmado: EUA, região US East (Virginia) | Sim | Enquanto a infraestrutura estiver ativa; logs seguem período próprio da plataforma (não confirmado) |
| **Sentry** | Monitoramento de erros técnicos | Dados técnicos (URL, stack trace); PII automático desabilitado (`send_default_pii=False`) — pode conter dado pessoal apenas se aparecer incidentalmente no texto de um erro | Empresa americana/com operação na UE | Provavelmente sim (não confirmado o local exato de processamento da conta usada) | Não confirmada (depende do plano/configuração da conta Sentry) |
| **Armazenamento de mídia (S3-compatível)** | Guarda os GIFs/imagens dos exercícios (biblioteca do app, não dados pessoais de usuário) | Nenhum dado pessoal — apenas mídia genérica de exercícios | **NÃO CONFIRMADO** — a variável `S3_ENDPOINT_URL` define o provedor real, e esse valor não é algo que eu tenha acesso para confirmar qual serviço/país é | Não confirmado | Não confirmado |

## Observações

- Fotos enviadas pelo usuário ao FitBot **não são armazenadas** em nenhum lugar (nem
  banco, nem S3) — existem só em memória durante o processamento da requisição e são
  repassadas ao provedor de IA. Confirmado lendo `services/fitbot_service.py`.
- Este documento não substitui a análise de um advogado quanto às hipóteses do Art. 33
  da LGPD aplicáveis a cada transferência internacional listada acima.
- Onde consta "NÃO CONFIRMADO", isso significa que a informação não pôde ser verificada
  a partir do código-fonte ou de documentação seguramente atribuível ao fornecedor — não
  significa que o dado não existe, apenas que não deve ser publicado sem confirmação.