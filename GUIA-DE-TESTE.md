# Guia de teste

Obrigado por ajudar a testar! Este guia explica, passo a passo, como pôr o site a funcionar no seu
computador e o que experimentar. Não é preciso saber nada de programação.

**O que é o projeto:** um site que compara os preços de videojogos em várias lojas portuguesas
(Press Start, Mega Mania, CSTech, Gaming Replay, Rádio Popular) e onde os utilizadores podem
vender os seus jogos usados uns aos outros.

**A versão de teste:** o site funciona só no seu computador, com os preços que já foram recolhidos
das lojas (não vai buscar preços novos). Nada do que fizer é visto por outras pessoas nem chega às lojas.

> **Recebeu um link para o site?** Então não precisa de instalar nada: abra o link, escreva o
> utilizador e a palavra-passe que recebeu e passe diretamente ao
> [Passo 5 — O que testar](#passo-5--o-que-testar). Nesse caso, o site é partilhado pelo grupo de
> teste: os outros testadores veem os anúncios e contas que criar.

---

## Antes de começar

- Um computador com **Windows 10 ou 11**, ou um **Mac** (de 2020 ou mais recente, de preferência)
- Pelo menos **8 GB de memória** e **3 GB livres** no disco
- Ligação à internet
- Cerca de **20 minutos** da primeira vez (a maior parte é a instalar o Docker); das outras vezes, 1 minuto
- O ficheiro **`demo.json.gz`**, que recebeu de quem lhe enviou este guia (são os jogos e preços)

---

## Passo 1 — Instalar o Docker Desktop

O Docker Desktop é um programa gratuito que corre o site e a sua base de dados sem instalar mais nada.

### Windows

1. Abra <https://www.docker.com/products/docker-desktop/> e carregue em **Download for Windows**
   (se perguntar, escolha **AMD64**, que é a da maioria dos computadores).
2. Abra o ficheiro descarregado (`Docker Desktop Installer.exe`) e aceite as opções que vêm marcadas.
3. No fim, o instalador pode pedir para **reiniciar o computador**. Reinicie.
4. Abra o **Docker Desktop** (menu Iniciar). Da primeira vez:
   - aceite os termos (**Accept**);
   - se pedir para iniciar sessão ou criar conta, pode carregar em **Skip** (não é preciso conta);
   - se aparecer uma mensagem sobre o **WSL** a pedir uma atualização, carregue no botão que ela
     indica e aguarde.
5. Está pronto quando, no canto inferior esquerdo da janela do Docker, aparecer **Engine running**
   (ou um ícone verde).

### Mac

1. Abra <https://www.docker.com/products/docker-desktop/> e carregue em **Download for Mac**.
   Escolha **Apple Silicon** se o Mac tiver um chip M1, M2, M3 ou M4, ou **Intel** se não tiver
   (para saber:  → **Acerca deste Mac**, linha "Chip" ou "Processador").
2. Abra o ficheiro `.dmg` e arraste o Docker para a pasta **Aplicações**.
3. Abra o **Docker** a partir das Aplicações, aceite os termos e, se pedir conta, carregue em **Skip**.

---

## Passo 2 — Descarregar o projeto

1. Abra <https://github.com/Barbaaz/Project-10794>.
2. Carregue no botão verde **Code** e depois em **Download ZIP**.
3. Descompacte o ZIP:
   - **Windows:** clique com o botão direito no ficheiro → **Extrair tudo...** → **Extrair**.
     (Não use os ficheiros de dentro do ZIP sem os extrair: não funciona.)
   - **Mac:** basta fazer duplo clique no ZIP.
4. Fica com uma pasta chamada **Project-10794-main**. Pode pô-la onde quiser (por exemplo nos Documentos).

## Passo 3 — Colocar o ficheiro dos dados

1. Dentro da pasta **Project-10794-main**, abra a pasta **database** e depois a pasta **demo**
   (se a pasta `demo` não existir, crie-a com esse nome).
2. Copie para lá o ficheiro **`demo.json.gz`** que recebeu. **Não o descompacte.**
   (No Mac, o Safari pode descompactá-lo sozinho e chamar-lhe `demo.json`: também serve.)

O caminho final fica: `Project-10794-main` → `database` → `demo` → `demo.json.gz`

---

## Passo 4 — Ligar o site

### Windows

1. Abra a pasta **Project-10794-main** → **teste**.
2. Faça duplo clique em **INICIAR.bat**.
   - Se aparecer "**O Windows protegeu o seu PC**", carregue em **Mais informações** → **Executar mesmo assim**.
   - Se aparecer "Aviso de Segurança - Abrir Ficheiro", carregue em **Executar**.
3. Abre-se uma janela preta com texto. **Não a feche** e espere: da primeira vez demora alguns
   minutos (descarrega cerca de 300 MB). Se o Docker Desktop não estiver aberto, a janela abre-o sozinha.
4. Quando estiver pronto, o site abre-se no navegador em **<http://localhost:8010>** e a janela
   preta diz "O site está aberto no navegador". Já a pode fechar.

### Mac

1. Abra a pasta **Project-10794-main** → **teste**.
2. **Da primeira vez:** clique com o **botão direito** (ou Control + clique) em **iniciar.command**
   → **Abrir** → **Abrir**. (Com duplo clique, o Mac diz que o ficheiro é de um "programador não
   identificado" e não o deixa abrir.) Das outras vezes, basta o duplo clique.
3. Abre-se o Terminal com texto. **Não o feche** e espere, como no Windows. No fim, o site abre-se
   em **<http://localhost:8010>**.

> Se o Mac disser que não tem permissão para abrir o ficheiro: abra o **Terminal** (Aplicações →
> Utilitários), escreva `sh ` (com um espaço no fim), arraste o ficheiro **iniciar.command** para
> a janela do Terminal e carregue em Enter.

Sabe que está na versão de teste pela faixa azul no topo de cada página ("🧪 Versão de teste").

---

## Passo 5 — O que testar

Experimente à vontade: não há nada que se possa estragar. Abaixo há uma lista de sugestões; marque
o que fez e anote tudo o que lhe pareça estranho, confuso, lento ou errado, mesmo que seja pequeno
(uma palavra mal escrita, um botão difícil de encontrar).

### A. Procurar e comparar preços (sem conta)

- [ ] Percorra os separadores da página inicial: **Melhores preços**, **Pré-reservas**,
      **Lançamentos**, **Catálogo**, **Edições especiais**, **Consolas**
- [ ] Pesquise um jogo na caixa **Procurar um jogo…**, no topo (por exemplo "zelda", "fifa", "mario")
      e mude a ordenação (nome / preço)
- [ ] Use os filtros: a **plataforma** (PS5, Switch... por cima dos jogos; as mais antigas em
      **Outras**), e no Catálogo a **loja**, a **categoria**, as **etiquetas** e a **Idade** (PEGI)
- [ ] Abra a página de um jogo: à direita, a **caixa de compra** (o melhor preço, as **edições**
      Standard, Deluxe..., o preço em cada loja); à esquerda, a descrição, as **imagens e os vídeos**;
      no fim, o **gráfico de preços** (passe o rato, ou o dedo, por cima de um dia)
- [ ] Carregue numa loja (ou em "Ver na …"): abre a página verdadeira da loja (o preço lá pode já ser outro)
- [ ] Mude o idioma (**PT / EN**) e ligue o **modo escuro**
- [ ] Torne a janela do navegador estreita, do tamanho de um telemóvel: tudo continua legível,
      sem ter de deslizar para os lados?

### B. Conta, coleção e lista de desejos

- [ ] Crie uma conta (**Entrar** → **Criar conta**). Pode usar um e-mail inventado: não é enviado nenhum e-mail
- [ ] Saia e volte a entrar
- [ ] Na estrela ☆ de um jogo, escolha **⭐ Quero** (lista de desejos) e **📚 Tenho** (coleção)
- [ ] Abra a sua coleção (**Coleção**, no topo; 📚 num telemóvel): mude o estado de um jogo, as horas jogadas, as notas
- [ ] Num jogo que existe em várias plataformas, carregue nos botões das plataformas no cartão
      (PS5, Switch 2...): os preços mudam para essa plataforma
- [ ] Veja o separador **Lista de desejos** na página inicial
- [ ] Escreva uma **crítica** de um jogo (nota de 1 a 10) na página do jogo
- [ ] Em **A minha conta**, descarregue **os seus dados** (um ficheiro com tudo o que o site guarda sobre si)

### C. Mercado de usados

Já existem utilizadores de demonstração, com anúncios e conversas: entre como **demo_ana**,
**demo_bruno**, **demo_carla**, **demo_diogo** ou **demo_eva**, todos com a palavra-passe
**demo12345**.

- [ ] Veja o separador **Usados** e abra um anúncio
- [ ] Com a sua conta, envie uma mensagem a um vendedor e carregue em **Comprar**
- [ ] Na conversa, peça mais fotografias; como vendedor, envie-as com o botão **📷** (do telemóvel também)
- [ ] Ponha um jogo seu à venda (**Vender**, no topo (🏷️ num telemóvel), **🏷️ Vender** na estrela ☆ de um jogo, ou **Vender este jogo** na página de um jogo; se a sua edição não aparecer, veja "Outras edições (do IGDB)"): são precisas pelo menos 3 fotografias (servem
      quaisquer fotografias do computador ou do telemóvel)
- [ ] Faça uma compra completa, do pedido à avaliação. Para fazer de comprador e de vendedor ao
      mesmo tempo, abra uma **janela anónima / privada** do navegador (Ctrl+Shift+N no Chrome e no
      Edge, ⌘+Shift+N no Mac) e entre lá com outra conta. Os passos são: **Pedir para comprar** (comprador) →
      **Aceitar pedido** (vendedor) → **Marcar como enviado / entregue** (vendedor) → **Confirmar que
      recebi** (comprador) → os dois avaliam-se
- [ ] Veja o perfil público de um vendedor (carregue no nome dele)
- [ ] Denuncie um anúncio ou um utilizador (botão **Denunciar**)

### D. Moderação

- [ ] Entre como **demo_eva** (é moderadora) e, no menu da conta (o botão com o nome, no topo), escolha **🛡️ Moderação**: veja as denúncias
      (incluindo a que fez em C), as compras com problemas e o registo

---

## Passo 6 — Enviar o que encontrou

Envie as suas notas a quem lhe pediu o teste (por e-mail ou mensagem). Para cada problema, ajuda
muito saber:

1. **O que estava a fazer** (por exemplo: "pesquisei 'zelda' e filtrei por Switch")
2. **O que esperava** que acontecesse
3. **O que aconteceu**
4. Uma **captura de ecrã** (Windows: tecla Windows + Shift + S; Mac: ⌘ + Shift + 4)
5. O **computador** (Windows ou Mac) e o **navegador** (Chrome, Edge, Safari, Firefox)

Opiniões também contam: o que gostou, o que não percebeu, o que faltou.

---

## Desligar, recomeçar e desinstalar

| Quero... | Windows (pasta `teste`) | Mac (pasta `teste`) |
|----------|-------------------------|---------------------|
| **Desligar** o site (o que fiz fica guardado) | **PARAR.bat** | **parar.command** |
| **Voltar a ligar** | **INICIAR.bat** | **iniciar.command** |
| **Apagar** o que fiz e recomeçar do zero | **REPOR.bat** | **repor.command** |

Fechar o Docker Desktop também desliga o site. Ao reiniciar o computador, o site fica desligado
até voltar a abrir o INICIAR.

**Desinstalar tudo no fim:** desinstale o Docker Desktop como qualquer outro programa (no Mac:
Docker → ícone do inseto 🐞 **Troubleshoot** → **Uninstall**), o que apaga também o site e os
dados de teste, e apague a pasta **Project-10794-main**.

---

## Se alguma coisa correr mal

| O que aparece | O que fazer |
|---------------|-------------|
| "O Docker Desktop não está instalado" | Volte ao passo 1. Se o instalou agora, reinicie o computador |
| "O Docker Desktop não respondeu" | Abra o Docker Desktop à mão, espere por **Engine running** e abra outra vez o INICIAR |
| O Docker Desktop fala em **virtualização** ou **WSL** e não arranca | O computador precisa de uma opção ligada (virtualização). Fale com quem lhe pediu o teste |
| "Falta o ficheiro de dados" | Veja o passo 3: o ficheiro tem de estar em `database` → `demo` |
| "Alguma coisa correu mal" | Tire uma captura de ecrã da janela e envie-a |
| O navegador diz "Não é possível aceder a este site" | O site ainda está a arrancar: espere um minuto e atualize a página. Se continuar, abra outra vez o INICIAR |
| O primeiro arranque está muito lento | É normal da primeira vez (descarga de ~300 MB). Das outras vezes demora cerca de um minuto |
| O computador fica lento | O Docker usa bastante memória: desligue o site com o PARAR quando não estiver a testar |

**Coisas que são assim de propósito** (não é preciso reportar):

- Os preços **não são atualizados**: são os da data indicada na faixa azul, por isso podem ser
  diferentes dos das lojas.
- O separador de descontos mostra "**melhores preços entre lojas**": um desconto só conta quando o
  preço fica abaixo do mais baixo dos 30 dias anteriores, e o histórico de preços ainda é curto.
- **Não são enviados e-mails** (nem para recuperar a palavra-passe).
- As fotografias dos anúncios dos utilizadores demo são desenhos com a palavra **DEMO**.
