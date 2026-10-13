# FLOAT

Aplicativo local para Windows 11, com controle do mouse por uma mão, comandos de voz e ditado em português brasileiro.

## Abrir e configurar

1. Abra `dist\FLOAT\FLOAT.exe` (ou `FLOAT.exe` dentro da pasta do pacote).
2. Aguarde os estados de câmera, voz e ditado ficarem prontos.
3. Escolha sua mão. A prévia é espelhada; a mão selecionada recebe o desenho dos pontos.
4. Na imagem, arraste um retângulo delimitando a área em que sua mão se move confortavelmente.
5. Ajuste sensibilidade e suavização, confira o nível do microfone e clique em **Salvar configuração**.
6. Diga **“computador, ativar”**. A configuração inicial é a única etapa que exige mouse e teclado físicos.

Ao salvar, a opção **Iniciar após meu login no Windows** registra a inicialização para seu usuário. O FLOAT abre pausado e fica disponível na bandeja. Desmarque a opção e salve para remover a inicialização automática. Mantenha a pasta completa do aplicativo no mesmo local; se movê-la, abra o executável no novo local e salve novamente.

Fechar a janela de configuração apenas a recolhe para a bandeja. Para liberar câmera e microfone, use **Encerrar FLOAT** na bandeja ou diga **“computador, encerrar controle”**. A pausa mantém a escuta disponível para retomar. `Ctrl+Alt+P` é a pausa de emergência.

## Gestos

| Ação | Gesto |
|---|---|
| Mover | Indicador estendido, outros dedos recolhidos |
| Clique | Pinça breve entre polegar e indicador, depois soltar |
| Clique duplo | Duas pinças breves no mesmo ponto |
| Arrastar | Manter a pinça por 350 ms, mover e soltar |
| Clique direito | Pinça entre polegar e médio, depois soltar |
| Rolar | Indicador e médio estendidos; subir/descer a mão |

Aponte antes de fazer a primeira pinça. A palma e os dedos precisam permanecer visíveis. Quando a mão desaparece por 250 ms, qualquer botão mantido pelo FLOAT é liberado. O cursor fica limitado ao monitor principal.

## Voz e ditado

Todo comando começa com **computador**. Exemplos:

- `ativar`, `pausar`, `retomar`, `abrir configurações`, `encerrar controle`;
- `clicar`, `clique duplo`, `clique direito`, `rolar para baixo`, `rolar para cima`;
- `abrir navegador`, `abrir explorador`, `abrir bloco de notas`, `abrir calculadora`;
- `alternar janela`, `minimizar janela`, `maximizar janela`, `restaurar janela`, `fechar janela`;
- `copiar`, `colar`, `recortar`, `selecionar tudo`, `desfazer`, `refazer`, `apagar última palavra`;
- `enter`, `próximo campo` (Tab), `escape`, `espaço`, `apagar`, `excluir` (Delete), `início`, `fim`, `seta acima`, `seta abaixo`, `seta esquerda`, `seta direita`;
- `vírgula`, `ponto final`, `dois pontos`, `ponto e vírgula`, `interrogação`, `exclamação`, `nova linha`.

Clique em um campo e diga **“computador, iniciar ditado”**. Fale uma frase e faça uma breve pausa. O painel informa a transcrição e a inserção. **“Computador, terminar ditado”** aguarda as frases anteriores antes de encerrar. **“Computador, pausar”** cancela imediatamente o que ainda não foi inserido.

Se a janela ativa mudar, o ditado é suspenso e transcrições pendentes são descartadas. Clique no novo campo e diga **“computador, continuar ditado”**. A verificação acompanha janelas do Windows; mover o foco entre campos da mesma janela exige atenção ao campo selecionado.

Frases iniciadas por “computador” são reservadas para comandos. `Nova linha` envia Shift+Enter; `enter` envia Enter, conforme o comportamento do aplicativo de destino. O FLOAT não altera a área de transferência ao ditar. Aplicativos adicionais podem ser cadastrados com nomes de fala e caminhos `.exe` ou `.lnk`.

## Privacidade e limites

- Câmera, microfone, reconhecimento e ditado funcionam localmente. O uso não exige internet, conta, chave de API ou assinatura.
- A preparação baixa modelos públicos. O executável carrega apenas os modelos da pasta `models`, sem downloads em segundo plano.
- Áudio, vídeo e transcrições são mantidos apenas em memória e não são registrados em arquivos de diagnóstico.
- Configuração e diagnósticos técnicos ficam em `%LOCALAPPDATA%\FLOAT`.
- Controle destinado à sessão desbloqueada e a aplicativos com permissões normais. Login, telas seguras e janelas elevadas não são controlados.
- O reconhecimento depende de iluminação, enquadramento, distância e ruído. As metas de fluidez e precisão precisam ser confirmadas com a mão e a voz do usuário.

## Desenvolvimento

Requer Windows x64 e Python 3.12. Em uma instalação nova:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe scripts\prepare_models.py
.\.venv\Scripts\python.exe run_float.py
```

Nesta máquina, a unidade C: estava quase cheia. As pastas `.venv`, `.cache`, `models`, `build` e `dist` são vínculos para `D:\FLOAT-local`; o código permanece em `C:\Users\Geovano\FLOAT`. O arquivo local `.storage-path` registra esse destino. Não apague a pasta de D: enquanto usar estes vínculos. O pacote em `dist\FLOAT` é independente do ambiente de desenvolvimento.

Para testar e empacotar:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run_float.py --self-test artifacts\source-self-test.json
.\.venv\Scripts\python.exe scripts\build.py
.\dist\FLOAT\FLOAT.exe --self-test artifacts\packaged-self-test.json
```

Adicione `--probe-devices` ao autoteste para abrir a webcam e capturar 0,2 segundo de áudio sem salvar imagens ou áudio. O autoteste bloqueia conexões e resolução DNS de Python, carrega todos os modelos locais e verifica o processamento de silêncio. Ele não move o mouse nem digita.

`scripts\make_voice_fixtures.ps1` e `scripts\test_voice_models.py` testam os reconhecedores com a voz sintética pt-BR instalada no Windows. Esses testes não substituem uma sessão com a voz real do usuário.

Arquitetura: `gestures.py` contém a máquina de gestos pura; `workers.py` mantém captura e inferência fora da interface; `app.py` coordena modos e invalidação; `windows.py` concentra toda a entrada Windows. As filas têm limites, a câmera mantém apenas o quadro mais recente, e cada trecho de áudio carrega a geração do modo em que foi capturado.

## Validação de uso diário

Após calibrar, realizar 20 minutos sem mouse e teclado físicos: abrir aplicativos, alternar janelas, clicar e dar clique duplo, arrastar um item de teste, rolar uma página, ditar um parágrafo e corrigi-lo. Verificar também pausa, retomada, perda da mão e troca de janela durante a transcrição.

Metas no hardware do usuário: ponteiro abaixo de 150 ms, comando até 1,5 s após a fala e frase curta ditada até 3 s após a fala. Tempos de inferência isolados e fala sintética não comprovam essas metas no uso real. Consulte `VALIDATION.md` no projeto para os resultados efetivamente obtidos.

