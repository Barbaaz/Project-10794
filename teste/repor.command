#!/bin/sh
# Deletes the test copy's data (accounts, listings, messages made while testing) and starts
# again from the demo data.
cd "$(dirname "$0")/.." || exit 1
echo "Isto apaga tudo o que foi feito no site de teste (contas, anúncios, mensagens)"
echo "e recomeça com os dados de demonstração."
echo
printf "Quer continuar? Escreva S e carregue em Enter: "
read -r answer
case "$answer" in
    s|S) docker compose down -v && exec sh teste/iniciar.command ;;
    *) echo "Nada foi apagado." ;;
esac
