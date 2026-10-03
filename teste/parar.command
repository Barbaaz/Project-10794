#!/bin/sh
# Stops the test copy (what was done on the site is kept for the next start).
cd "$(dirname "$0")/.." || exit 1
docker compose stop
echo
echo "O site foi desligado. O que fez fica guardado para a próxima vez (teste/iniciar.command)."
echo
printf "Carregue em Enter para fechar esta janela. "
read -r _
