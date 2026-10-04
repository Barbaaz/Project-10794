#!/bin/sh
# Starts the test copy of the site on demo data (Docker) and opens it in the browser.
# macOS: double-click it (the first time: right-click → Abrir). Linux: sh teste/iniciar.command
# Explained in GUIA-DE-TESTE.md.
cd "$(dirname "$0")/.." || exit 1
SITE=http://localhost:8010

open_url() { open "$1" 2>/dev/null || xdg-open "$1" >/dev/null 2>&1; }
finish() { echo; printf "Carregue em Enter para fechar esta janela. "; read -r _; exit "$1"; }

if ! command -v docker >/dev/null 2>&1; then
    echo "O Docker Desktop não está instalado. Veja o passo 1 do GUIA-DE-TESTE.md."
    open_url https://www.docker.com/products/docker-desktop/
    finish 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "A abrir o Docker Desktop..."
    open -a Docker 2>/dev/null
    tries=0
    until docker info >/dev/null 2>&1; do
        tries=$((tries + 1))
        if [ $tries -ge 36 ]; then
            echo "O Docker Desktop não respondeu. Abra-o à mão, espere que diga que está a correr"
            echo "e abra outra vez este ficheiro."
            finish 1
        fi
        sleep 5
    done
fi

if [ ! -f database/demo/demo.json.gz ] && [ ! -f database/demo/demo.json ]; then
    mkdir -p database/demo
    echo "Falta o ficheiro de dados: demo.json.gz"
    echo "Coloque o ficheiro que recebeu na pasta que se vai abrir agora (database/demo)"
    echo "e abra outra vez este ficheiro."
    open_url database/demo
    finish 1
fi

# Passwords for this computer only, made the first time
if [ ! -f .env ]; then
    random() { od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; }
    {
        echo "# Feito por teste/iniciar.command para a versão de teste neste computador. Nunca o partilhe."
        echo "DB_PASSWORD=Teste-$(random 8)-Aa1"
        echo "SECRET_KEY=$(random 32)"
    } > .env
fi

echo
echo "A preparar o site. Da primeira vez demora alguns minutos (descarrega cerca de 300 MB);"
echo "depois é rápido. Não feche esta janela."
echo
if ! DEMO_MODE=1 WEB_PORT=8010 docker compose up --build -d; then
    failed=1
else
    echo
    echo "A aguardar que o site arranque..."
    tries=0
    until curl -s -f -o /dev/null "$SITE/api/demo"; do
        tries=$((tries + 1))
        if [ $tries -ge 120 ]; then failed=1; break; fi
        sleep 5
    done
fi

if [ -n "$failed" ]; then
    echo
    echo "Alguma coisa correu mal. Últimas linhas do registo do site:"
    echo
    docker compose logs --tail 30 web
    echo
    echo "Tire uma captura de ecrã a esta janela e envie-a a quem lhe pediu o teste."
    finish 1
fi

open_url "$SITE"
echo
echo "============================================================"
echo " O site está aberto no navegador: $SITE"
echo " Pode fechar esta janela; o site continua a funcionar."
echo " Para o desligar: abra teste/parar.command"
echo "============================================================"
finish 0
