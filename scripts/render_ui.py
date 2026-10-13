"""Render the actual Qt widgets offscreen for layout review; no desktop capture."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from float_app.config import Settings
from float_app.ui import SettingsWindow, Overlay

app = QApplication([])
for filename in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / filename))
window = SettingsWindow(Settings())
window.camera_status.setText('Câmera conectada')
window.voice_status.setText('Microfone conectado • diga “computador, ativar”')
window.dictation_status.setText('Ditado pronto • português, processamento local')
window.status.setText('PAUSADO  ·  Calibre a área e salve a configuração')
window.show()
output = Path(__file__).resolve().parents[1] / 'artifacts'
output.mkdir(exist_ok=True)
for index, name in enumerate(('control', 'applications', 'guide')):
    window.tabs.setCurrentIndex(index)
    app.processEvents()
    window.grab().save(str(output / f'ui-{name}.png'))
overlay = Overlay()
overlay.show()
app.processEvents()
overlay.grab().save(str(output / 'ui-overlay.png'))
print('Rendered 4 Qt widget images.')

