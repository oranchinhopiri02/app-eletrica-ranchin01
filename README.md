# App Custos Ranchin

Dashboard Streamlit conectado à planilha Google Sheets.

## Arquivos
- `app.py`: aplicação do dashboard.
- `requirements.txt`: dependências.

## Configuração segura para publicação
1. Crie uma conta de serviço no Google Cloud e habilite a Google Sheets API.
2. Baixe o JSON da conta de serviço.
3. Compartilhe a planilha com o e-mail `client_email` da conta de serviço, com permissão de Leitor.
4. No Streamlit Community Cloud, abra **App > Settings > Secrets** e cole o conteúdo JSON no formato TOML:

```toml
[gcp_service_account]
type = "service_account"
project_id = "SEU_PROJECT_ID"
private_key_id = "SUA_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "EMAIL_DA_CONTA_DE_SERVICO"
client_id = "SEU_CLIENT_ID"
token_uri = "https://oauth2.googleapis.com/token"
```

Inclua também os demais campos do JSON original, mantendo os nomes e valores originais.
Nunca publique o JSON da conta de serviço no GitHub nem compartilhe a chave privada.

## Publicação
1. Coloque `app.py` e `requirements.txt` em um repositório GitHub privado.
2. Conecte o repositório ao Streamlit Community Cloud.
3. Selecione `app.py` como arquivo principal.
4. Configure os Secrets conforme acima.
5. Depois de publicar, use a URL HTTPS do app para incorporar no Google Sites.

O app usa cache de 5 minutos e tem botão para atualização manual.
