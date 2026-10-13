# Componentes do FLOAT

Este pacote usa bibliotecas e modelos de terceiros. As licenças fornecidas pelas distribuições Python estão na pasta `licenses`; as versões efetivamente empacotadas estão em `dependencies.json`.

- Qt for Python / PySide6 Essentials: LGPLv3/GPLv3 ou licença comercial, conforme os componentes. https://www.qt.io/licensing/
- MediaPipe e modelo Hand Landmarker: Apache 2.0. https://github.com/google-ai-edge/mediapipe
- Vosk API e `vosk-model-small-pt-0.3`: Apache 2.0. https://github.com/alphacep/vosk-api e https://alphacephei.com/vosk/models
- faster-whisper: MIT. https://github.com/SYSTRAN/faster-whisper
- Modelo Whisper small convertido por SYSTRAN: origem OpenAI Whisper, MIT. https://huggingface.co/Systran/faster-whisper-small e https://github.com/openai/whisper
- CTranslate2: MIT. https://github.com/OpenNMT/CTranslate2
- OpenCV: Apache 2.0. https://opencv.org/license/
- sounddevice: MIT; PortAudio: MIT. https://python-sounddevice.readthedocs.io/
- WebRTC VAD / webrtcvad-wheels: MIT e avisos BSD do WebRTC. https://github.com/daanzu/py-webrtcvad-wheels
- PyInstaller: GPL com exceção para distribuição dos aplicativos gerados. https://pyinstaller.org/en/stable/license.html

O diretório `models` contém os pesos locais; `models/manifest.json` identifica os arquivos por SHA-256. O FLOAT não reivindica autoria das bibliotecas ou dos modelos.

