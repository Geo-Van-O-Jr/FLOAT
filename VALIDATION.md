# Validação do FLOAT — 12/10/2026

## Executado nesta máquina

- 35 testes automatizados passaram: gestos, pinça curta/longa, tremor, rolagem, perda da mão, liberação de botões, comandos, invalidação de filas e suspensão por troca de janela.
- Webcam USB: 30 quadros reais em 640 × 480. Inferência da mão: mediana 9,4 ms e percentil 95 de 22,1 ms. Isso não mede a latência completa do ponteiro.
- Microfone USB: captura real bem-sucedida após liberar o acesso nas configurações do Windows. O trabalhador de áudio também iniciou, entregou 64 atualizações de nível e encerrou normalmente, sem salvar áudio.
- Modelos MediaPipe, Vosk e Whisper small CPU/int8 carregados dos arquivos locais. Autoteste com conexões e DNS de Python bloqueados passou; esse bloqueio não equivale a desconectar a rede inteira do Windows.
- Voz sintética pt-BR: 20/20 comandos reconhecidos e 3/3 frases comuns ignoradas. Não substitui o teste com a voz do usuário em diferentes condições de ruído.
- Whisper transcreveu corretamente uma amostra com acentos. Processamento: 2.168 ms, sem incluir captura nem espera pelo fim da fala. Vosk: aproximadamente 182–646 ms por comando nessa amostra.
- Interface conferida por árvore de acessibilidade e renderização dos componentes Qt. A captura visual da área de trabalho não estava disponível nesta sessão. Pausa de emergência Ctrl+Alt+P confirmada na aplicação aberta.
- Calibração e preferências salvas pelo usuário foram preservadas.
- Registro de inicialização do usuário conferido: aponta para `dist/FLOAT/FLOAT.exe --background`, conforme a preferência salva. A execução após um novo login ainda precisa de validação real.
- Pacote `dist/FLOAT/FLOAT.exe` gerado com dependências e modelos. Seu autoteste também passou com webcam, microfone e todos os modelos locais, sem erros. Na amostra empacotada, inferência da mão: mediana 10,9 ms e percentil 95 de 12,3 ms. Relatório: `artifacts/packaged-self-test.json`.

Relatórios técnicos em `artifacts/source-self-test.json`, `artifacts/audio-worker-test.json` e `artifacts/synthetic-voice-test.json`. Os arquivos de fala sintética são exclusivamente frases de teste; não contêm gravações do usuário.

## Aceitação que depende do uso real

Ainda não foram concluídos: sessão de 20 minutos sem periféricos físicos; ditado e correções no Bloco de Notas e navegador; desconexão física da câmera durante arraste; login real após reinicialização; medição completa das metas de 150 ms / 1,5 s / 3 s. Esses itens não são considerados aprovados pelos testes automatizados.

Para o teste final, use uma pasta e documentos de teste, ative com “computador, ativar” e percorra a lista em `README.md`. O comando “computador, pausar” e Ctrl+Alt+P permitem pausar o controle. A inicialização automática pode ser desativada nas configurações.
