from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QLineEdit, QMessageBox, QHeaderView,
    QProgressBar, QTextBrowser, QScrollArea,
)

from .commands import CommandParser
from .config import Settings

STYLE = """
QWidget { background: #111821; color: #eaf1f7; font: 10pt 'Segoe UI'; }
QLabel#brand { font-size: 25pt; font-weight: 700; color: #70e1d1; }
QLabel#subtitle, QLabel#hint { color: #a6b8c9; }
QPushButton { background: #243446; border: 1px solid #3d5063; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #304961; }
QPushButton#primary { background: #64d5c5; color: #0b2826; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #91e7db; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #1b2836; border: 1px solid #42566a; border-radius: 5px; padding: 5px; }
QComboBox QAbstractItemView { background: #1b2836; selection-background-color: #315b65; }
QTabWidget::pane { border: 1px solid #2b3d4e; border-radius: 6px; }
QTabBar::tab { background: #172331; padding: 9px 22px; margin-right: 3px; }
QTabBar::tab:selected { background: #2b4654; color: #88e9dc; }
QProgressBar { border: none; background: #263848; border-radius: 4px; max-height: 8px; }
QProgressBar::chunk { background: #64d5c5; border-radius: 4px; }
QTableWidget, QTextBrowser { background: #16222e; border: none; }
QHeaderView::section { background: #243446; color: #c9d9e5; padding: 6px; border: none; }
QScrollArea { border: none; }
QToolTip { background: #273c4a; color: white; border: 1px solid #64828e; }
"""


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#173a42"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, 62, 62, 16, 16)
    p.setPen(QPen(QColor("#70e1d1"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(21, 46, 21, 18)
    p.drawLine(21, 18, 44, 18)
    p.drawLine(21, 31, 38, 31)
    p.end()
    return QIcon(pixmap)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("FLOAT · Estado")
        self.setStyleSheet("QWidget { background: #14232d; color: #e7f4f3; font: 9pt 'Segoe UI'; } QLabel#mode { color: #70e1d1; font-weight: 700; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(3)
        self.mode = QLabel("FLOAT  ·  PAUSADO", objectName="mode")
        self.detail = QLabel("Diga “computador, ativar”")
        self.detail.setWordWrap(True)
        self.gesture = QLabel("Processamento local")
        layout.addWidget(self.mode)
        layout.addWidget(self.detail)
        layout.addWidget(self.gesture)
        self.setFixedSize(280, 96)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 14, screen.top() + 14)


class CameraPreview(QWidget):
    roi_changed = Signal(object)

    def __init__(self, roi):
        super().__init__()
        self.roi = list(roi)
        self.frame = None
        self.drag_start = None
        self.setMinimumSize(320, 240)
        self.setToolTip("Arraste um retângulo para definir a área confortável de movimento da mão.")
        self.setAccessibleName("Prévia da câmera e área de movimento")

    def image_rect(self) -> QRectF:
        ratio = 4 / 3
        if self.frame is not None:
            ratio = self.frame.image.shape[1] / self.frame.image.shape[0]
        width = min(self.width(), self.height() * ratio)
        height = width / ratio
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def position(self, event):
        rect = self.image_rect()
        point = event.position()
        return max(0, min(1, (point.x() - rect.x()) / rect.width())), max(0, min(1, (point.y() - rect.y()) / rect.height()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = self.position(event)

    def mouseMoveEvent(self, event):
        if self.drag_start:
            end = self.position(event)
            self.roi = [min(self.drag_start[0], end[0]), min(self.drag_start[1], end[1]), max(self.drag_start[0], end[0]), max(self.drag_start[1], end[1])]
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_start:
            self.mouseMoveEvent(event)
            self.drag_start = None
            self.roi_changed.emit(self.roi)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b1219"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.image_rect()
        if self.frame is not None:
            data = self.frame.image
            image = QImage(data.data, data.shape[1], data.shape[0], data.strides[0], QImage.Format.Format_RGB888)
            p.drawImage(rect, image)
            if self.frame.points:
                points = [QPointF(rect.x() + point.x * rect.width(), rect.y() + point.y * rect.height()) for point in self.frame.points]
                p.setPen(QPen(QColor("#7ef3d6"), 2))
                for finger in ([0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [5, 9, 10, 11, 12], [9, 13, 14, 15, 16], [13, 17, 18, 19, 20], [0, 17]):
                    for a, b in zip(finger, finger[1:]):
                        p.drawLine(points[a], points[b])
                p.setBrush(QColor("#f1ffff"))
                for point in points:
                    p.drawEllipse(point, 3, 3)
        else:
            p.setPen(QColor("#8096a9"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Aguardando câmera…")
        x1, y1, x2, y2 = self.roi
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#7ef3d6"), 2, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(rect.x() + x1 * rect.width(), rect.y() + y1 * rect.height(), (x2 - x1) * rect.width(), (y2 - y1) * rect.height()))
        p.end()


class SettingsWindow(QWidget):
    saved = Signal(object)
    toggle = Signal()
    retry = Signal()
    quit_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("FLOAT · Controle por mãos e voz")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.resize(1000, 620)
        self.setMinimumSize(850, 550)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.addWidget(QLabel("FLOAT", objectName="brand"))
        brand.addWidget(QLabel("Seu computador, nas suas mãos.", objectName="subtitle"))
        header.addLayout(brand)
        header.addStretch()
        self.toggle_button = QPushButton("Ativar controle")
        self.toggle_button.setObjectName("primary")
        self.toggle_button.clicked.connect(self.toggle.emit)
        header.addWidget(self.toggle_button)
        quit_button = QPushButton("Encerrar")
        quit_button.clicked.connect(self.quit_requested.emit)
        header.addWidget(quit_button)
        root.addLayout(header)
        self.status = QLabel("PAUSADO  ·  Preparando câmera e voz")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._control_tab()
        self._apps_tab()
        self._guide_tab()
        bottom = QHBoxLayout()
        self.feedback = QLabel("Ajuste a câmera e salve para concluir a configuração.")
        self.feedback.setWordWrap(True)
        self.feedback.setObjectName("hint")
        bottom.addWidget(self.feedback, 1)
        hide = QPushButton("Minimizar para bandeja")
        hide.clicked.connect(self.hide)
        bottom.addWidget(hide)
        save = QPushButton("Salvar configuração")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        bottom.addWidget(save)
        root.addLayout(bottom)

    def _control_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        left = QWidget()
        form = QFormLayout(left)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(12)
        self.camera = QSpinBox()
        self.camera.setRange(0, 20)
        self.camera.setValue(self.settings.camera_index)
        self.camera.setToolTip("A primeira webcam é a câmera 0. Mude somente se houver outra câmera.")
        form.addRow("Câmera", self.camera)
        self.microphone = QComboBox()
        self.microphone.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.microphone.setMinimumContentsLength(16)
        self.microphone.addItem("Microfone padrão do Windows", "")
        try:
            from .workers import microphones
            for label, name in microphones():
                self.microphone.addItem(label, name)
        except Exception:
            pass
        selected = self.microphone.findData(self.settings.microphone_name)
        if selected >= 0:
            self.microphone.setCurrentIndex(selected)
        form.addRow("Microfone", self.microphone)
        self.meter = QProgressBar()
        self.meter.setTextVisible(False)
        form.addRow("Nível de áudio", self.meter)
        self.hand = QComboBox()
        self.hand.addItem("Direita", "Right")
        self.hand.addItem("Esquerda", "Left")
        self.hand.setCurrentIndex(self.hand.findData(self.settings.gesture.hand))
        form.addRow("Mão de controle", self.hand)
        self.sensitivity = QDoubleSpinBox()
        self.sensitivity.setRange(0.4, 2)
        self.sensitivity.setSingleStep(0.1)
        self.sensitivity.setValue(self.settings.gesture.sensitivity)
        form.addRow("Sensibilidade", self.sensitivity)
        self.smoothing = QDoubleSpinBox()
        self.smoothing.setRange(0, 0.9)
        self.smoothing.setSingleStep(0.05)
        self.smoothing.setValue(self.settings.gesture.smoothing)
        form.addRow("Suavização", self.smoothing)
        self.drag = QSpinBox()
        self.drag.setRange(200, 900)
        self.drag.setSingleStep(50)
        self.drag.setSuffix(" ms")
        self.drag.setValue(self.settings.gesture.drag_ms)
        form.addRow("Tempo para arrastar", self.drag)
        self.startup = QCheckBox("Iniciar após meu login no Windows")
        self.startup.setChecked(self.settings.startup)
        form.addRow(self.startup)
        self.show_overlay = QCheckBox("Mostrar painel flutuante de estado")
        self.show_overlay.setChecked(self.settings.overlay)
        form.addRow(self.show_overlay)
        self.camera_status = QLabel("Câmera: preparando…")
        self.voice_status = QLabel("Voz: preparando…")
        self.dictation_status = QLabel("Ditado: preparando…")
        for label in (self.camera_status, self.voice_status, self.dictation_status):
            label.setWordWrap(True)
            label.setObjectName("hint")
            form.addRow(label)
        retry = QPushButton("Reiniciar dispositivos")
        retry.clicked.connect(self.retry.emit)
        form.addRow(retry)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(390)
        layout.addWidget(scroll)
        right = QVBoxLayout()
        self.preview = CameraPreview(self.settings.gesture.roi)
        right.addWidget(self.preview, 1)
        hint = QLabel("Calibração: arraste um retângulo na imagem para delimitar onde sua mão se move confortavelmente. Depois, salve.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        right.addWidget(hint)
        self.metrics = QLabel("Mantenha a mão inteira visível e bem iluminada.")
        self.metrics.setWordWrap(True)
        right.addWidget(self.metrics)
        reset = QPushButton("Restaurar área de movimento")
        reset.clicked.connect(lambda: self.reset_roi())
        right.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(right, 1)
        self.tabs.addTab(tab, "Controle")

    def reset_roi(self):
        self.preview.roi = [0.15, 0.15, 0.85, 0.85]
        self.preview.update()

    def _apps_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel("Diga “computador, abrir” seguido do nome cadastrado. Navegador, Explorador, Bloco de Notas e Calculadora já estão disponíveis.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.apps = QTableWidget(0, 2)
        self.apps.setHorizontalHeaderLabels(["Nome para falar", "Aplicativo ou atalho"])
        self.apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for alias, path in self.settings.applications.items():
            self.add_app_row(alias, path)
        layout.addWidget(self.apps, 1)
        row = QHBoxLayout()
        add = QPushButton("Adicionar aplicativo…")
        add.clicked.connect(self.browse_app)
        remove = QPushButton("Remover selecionado")
        remove.clicked.connect(lambda: self.apps.removeRow(self.apps.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.tabs.addTab(tab, "Aplicativos")

    def add_app_row(self, alias, path):
        row = self.apps.rowCount()
        self.apps.insertRow(row)
        self.apps.setItem(row, 0, QTableWidgetItem(alias))
        self.apps.setItem(row, 1, QTableWidgetItem(path))

    def browse_app(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Escolher aplicativo", "", "Aplicativos e atalhos (*.exe *.lnk)")
        if filename:
            self.add_app_row(Path(filename).stem, filename)
            self.apps.editItem(self.apps.item(self.apps.rowCount() - 1, 0))

    def _guide_tab(self):
        help_view = QTextBrowser()
        help_view.setHtml("""
        <h2>Comece com “computador, ativar”</h2>
        <p>Aponte com o indicador para mover. Junte polegar e indicador e solte para clicar;
        repita duas vezes para clique duplo. Mantenha a pinça por 350 ms para arrastar e solte
        para liberar. Junte polegar e médio para clique direito. Levante indicador e médio
        e mova a mão verticalmente para rolar. Recolha os outros dedos.</p>
        <h3>Comandos de voz</h3>
        <p>Comece cada comando com <b>computador</b>: ativar, pausar, retomar,
        abrir configurações, encerrar controle, clicar, clique duplo, clique direito,
        rolar para cima, rolar para baixo, alternar janela, minimizar janela,
        maximizar janela, restaurar janela e fechar janela.</p>
        <p>Para aplicativos: abrir navegador, abrir explorador, abrir bloco de notas,
        abrir calculadora ou abrir um nome cadastrado.</p>
        <h3>Escrever e corrigir</h3>
        <p>Clique no campo e diga <b>computador, iniciar ditado</b>. Fale uma frase e faça uma
        breve pausa. O texto é inserido após ser reconhecido. Diga <b>computador, terminar ditado</b>
        para voltar aos comandos. Se mudar de janela, clique no novo campo e diga
        <b>computador, continuar ditado</b>.</p>
        <p>Correções: copiar, colar, recortar, selecionar tudo, desfazer, refazer,
        apagar última palavra. Pontuação: vírgula, ponto final, dois pontos, ponto e vírgula,
        interrogação e exclamação. Use sempre “computador” antes desses comandos.</p>
        <p>Teclas: enter, próximo campo (Tab), escape, espaço, apagar, excluir (Delete), início, fim e setas.
        “Computador, nova linha” usa Shift+Enter. “Computador, enter” pressiona Enter.
        Frases que começam com “computador” são reservadas para comandos.</p>
        <h3>Pausa e privacidade</h3>
        <p>“Computador, pausar” interrompe o controle e solta os botões. O microfone permanece
        disponível para retomar. <b>Ctrl+Alt+P</b> também pausa imediatamente.
        Para liberar câmera e microfone, encerre o FLOAT pelo ícone na bandeja ou diga
        “computador, encerrar controle”. Áudio, vídeo e textos não são gravados.</p>
        <p>O FLOAT controla aplicativos da sessão desbloqueada. Janelas de administrador,
        login e telas seguras do Windows não são controladas.</p>
        """)
        self.tabs.addTab(help_view, "Guia")

    def save(self):
        result = copy.deepcopy(self.settings)
        result.camera_index = self.camera.value()
        result.microphone_name = self.microphone.currentData()
        result.gesture.hand = self.hand.currentData()
        result.gesture.roi = list(self.preview.roi)
        result.gesture.sensitivity = self.sensitivity.value()
        result.gesture.smoothing = self.smoothing.value()
        result.gesture.drag_ms = self.drag.value()
        result.startup = self.startup.isChecked()
        result.overlay = self.show_overlay.isChecked()
        result.applications = {}
        try:
            for row in range(self.apps.rowCount()):
                alias = self.apps.item(row, 0).text().strip()
                path = self.apps.item(row, 1).text().strip()
                if alias in result.applications:
                    raise ValueError("Há nomes de aplicativo repetidos.")
                if not Path(path).is_file() or Path(path).suffix.lower() not in (".exe", ".lnk"):
                    raise ValueError(f"Escolha um aplicativo ou atalho existente para {alias}.")
                result.applications[alias] = path
            CommandParser(result.applications)
            result.configured = True
            result.validate()
            self.saved.emit(result)
        except (ValueError, AttributeError) as exc:
            QMessageBox.warning(self, "Revise a configuração", str(exc))

    def closeEvent(self, event):
        self.hide()
        event.ignore()

