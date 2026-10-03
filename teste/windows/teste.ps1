# The Windows side of the test copy's launchers (teste\INICIAR.bat, PARAR.bat, REPOR.bat call it).
# PowerShell rather than batch: cmd jumps to the wrong lines in a UTF-8 file with accents.
# Explained in GUIA-DE-TESTE.md.
param([ValidateSet("iniciar", "parar", "repor")] [string]$Acao = "iniciar")

Set-Location (Resolve-Path "$PSScriptRoot\..\..")
$Site = "http://localhost:8010"
$Host.UI.RawUI.WindowTitle = "Versão de teste"

function Finish($code) {
    Write-Host ""
    Read-Host "Carregue em Enter para fechar esta janela" | Out-Null
    exit $code
}

function Failed {
    Write-Host ""
    Write-Host "Alguma coisa correu mal. Últimas linhas do registo do site:" -ForegroundColor Red
    Write-Host ""
    docker compose logs --tail 30 web
    Write-Host ""
    Write-Host "Tire uma captura de ecrã a esta janela e envie-a a quem lhe pediu o teste."
    Finish 1
}

function DockerRunning {
    docker info *> $null
    return $LASTEXITCODE -eq 0
}

function RandomHex($bytes) {
    $buffer = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}

function Start-TestSite {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "O Docker Desktop não está instalado. Veja o passo 1 do GUIA-DE-TESTE.md."
        Start-Process "https://www.docker.com/products/docker-desktop/"
        Finish 1
    }

    if (-not (DockerRunning)) {
        Write-Host "A abrir o Docker Desktop..."
        $desktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $desktop) { Start-Process $desktop }
        $tries = 0
        while (-not (DockerRunning)) {
            if (++$tries -ge 36) {
                Write-Host "O Docker Desktop não respondeu. Abra-o à mão, espere que diga que está a correr"
                Write-Host "e faça duplo clique outra vez em INICIAR.bat."
                Finish 1
            }
            Start-Sleep -Seconds 5
        }
    }

    if (-not (Test-Path "database\demo\demo.json.gz") -and -not (Test-Path "database\demo\demo.json")) {
        New-Item -ItemType Directory -Force "database\demo" | Out-Null
        Write-Host "Falta o ficheiro de dados: demo.json.gz"
        Write-Host "Coloque o ficheiro que recebeu na pasta que se vai abrir agora (database\demo)"
        Write-Host "e faça duplo clique outra vez em INICIAR.bat."
        Start-Process explorer.exe (Resolve-Path "database\demo")
        Finish 1
    }

    # Passwords for this computer only, made the first time
    if (-not (Test-Path ".env")) {
        $lines = @(
            "# Made by teste\INICIAR.bat for this computer's test copy. Never share it.",
            "DB_PASSWORD=Teste-$(RandomHex 8)-Aa1",
            "SECRET_KEY=$(RandomHex 32)"
        )
        [IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $lines, (New-Object Text.UTF8Encoding $false))
    }

    Write-Host ""
    Write-Host "A preparar o site. Da primeira vez demora alguns minutos (descarrega cerca de 1 GB);"
    Write-Host "depois é rápido. Não feche esta janela."
    Write-Host ""
    $env:DEMO_MODE = "1"
    $env:WEB_PORT = "8010"
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) { Failed }

    Write-Host ""
    Write-Host "A aguardar que o site arranque..."
    $tries = 0
    while ($true) {
        try {
            Invoke-WebRequest "$Site/api/demo" -UseBasicParsing -TimeoutSec 5 | Out-Null
            break
        } catch {
            if (++$tries -ge 120) { Failed }
            Start-Sleep -Seconds 5
        }
    }

    Start-Process $Site
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " O site está aberto no navegador: $Site" -ForegroundColor Green
    Write-Host " Pode fechar esta janela; o site continua a funcionar." -ForegroundColor Green
    Write-Host " Para o desligar: duplo clique em teste\PARAR.bat" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Finish 0
}

switch ($Acao) {
    "iniciar" { Start-TestSite }
    "parar" {
        docker compose stop
        Write-Host ""
        Write-Host "O site foi desligado. O que fez fica guardado para a próxima vez (teste\INICIAR.bat)."
        Finish 0
    }
    "repor" {
        Write-Host "Isto apaga tudo o que foi feito no site de teste (contas, anúncios, mensagens)"
        Write-Host "e recomeça com os dados de demonstração."
        Write-Host ""
        $answer = Read-Host "Quer continuar? Escreva S e carregue em Enter"
        if ($answer -notin @("s", "S")) {
            Write-Host "Nada foi apagado."
            Finish 0
        }
        docker compose down -v
        Start-TestSite
    }
}
