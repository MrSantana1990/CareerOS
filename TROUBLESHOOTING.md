# Solução de problemas

## Painel ou agente parado

```powershell
./scripts/start-background.ps1
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 3000,8765
```

## Celular não acessa

- Confirme que celular e computador estão no mesmo Wi‑Fi.
- Use o IPv4 da interface **Wi‑Fi**, não adaptadores virtuais.
- Teste `http://IP:3000`.
- Verifique regras do Firewall do Windows e não exponha a porta na internet.

## Google desconectado

- Confirme `.runtime/google/google-token.json`.
- Verifique se Gmail API e Calendar API estão ativas.
- Em app de teste, adicione a conta em **Usuários de teste**.
- Execute novamente `scripts/authorize-google.py` se o token for revogado.

## Questionário abre link errado

Clique em **Verificar agora**. O extrator atual bloqueia `xiti.com`, imagens e rodapés e prioriza `/Test` na Pandapé. `TestResult` significa concluído; 404/410 significa indisponível.

## IA local indisponível

Confirme `D:\DEV\IA-Local\runtime\llama-server.exe`, o modelo GGUF e a porta 8080. Consulte `server-error.log` na pasta da IA.

## Docker indisponível

Abra Docker Desktop e execute `docker info`. Para readiness 503, consulte `docker compose logs api postgres redis`.

## Porta ocupada

Identifique o processo com `Get-NetTCPConnection -LocalPort PORTA` e pare apenas o serviço conhecido. O script `stop.ps1` encerra os serviços CareerOS preservando dados.
