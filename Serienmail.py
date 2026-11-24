import sys
import time
import os
import csv
import json
import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QProgressBar, QMessageBox, QHeaderView, QComboBox, QFileDialog, QMenu, QCheckBox,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt5.QtCore import Qt

SETTINGS_FILE = "einstellungen.json"
RECIPIENTS_FILE = "empfaenger.json"
DRAFT_FILE = "entwurf.json"
ATTACHMENT_SIZE_WARNING_MB = 20  # Provider-Grenze, ab der gewarnt wird


class AttachmentDialog(QDialog):
    """Dialog zum Verwalten der Anhänge eines Empfängers:
    Dateiliste mit Hinzufügen, Entfernen und Sortieren."""

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anhänge verwalten")
        self.resize(520, 320)

        layout = QVBoxLayout(self)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.file_list)

        button_layout = QHBoxLayout()
        add_btn = QPushButton("Dateien hinzufügen...")
        add_btn.clicked.connect(self.add_files)
        button_layout.addWidget(add_btn)

        remove_btn = QPushButton("Auswahl entfernen")
        remove_btn.clicked.connect(self.remove_selected)
        button_layout.addWidget(remove_btn)

        up_btn = QPushButton("▲ Nach oben")
        up_btn.clicked.connect(lambda: self.move_selected(-1))
        button_layout.addWidget(up_btn)

        down_btn = QPushButton("▼ Nach unten")
        down_btn.clicked.connect(lambda: self.move_selected(1))
        button_layout.addWidget(down_btn)

        layout.addLayout(button_layout)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        for path in paths:
            self.file_list.addItem(QListWidgetItem(path))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Dateien auswählen", "", "Alle Dateien (*)"
        )
        for file_path in files:
            if self.file_list.findItems(file_path, Qt.MatchExactly):
                continue  # Duplikate überspringen
            self.file_list.addItem(QListWidgetItem(file_path))

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def move_selected(self, delta):
        rows = sorted(
            (self.file_list.row(item) for item in self.file_list.selectedItems()),
            reverse=(delta > 0)
        )
        for row in rows:
            new_row = row + delta
            if 0 <= new_row < self.file_list.count():
                item = self.file_list.takeItem(row)
                self.file_list.insertItem(new_row, item)
                item.setSelected(True)

    def get_paths(self):
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]


class RecipientTable(QTableWidget):
    """Empfängertabelle mit Drag & Drop: Dateien aus dem Dateimanager
    können direkt auf eine Zeile gezogen werden."""

    def __init__(self, parent=None):
        super().__init__(0, 6, parent)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def _is_file_drag(self, event):
        return event.mimeData().hasUrls() and any(
            u.toLocalFile() for u in event.mimeData().urls()
        )

    def dragEnterEvent(self, event):
        if self._is_file_drag(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._is_file_drag(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self._is_file_drag(event):
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if not paths:
            return
        row = self.rowAt(event.pos().y())
        if row < 0:
            # Unterhalb der Tabelle gezogen: neuen Empfänger anlegen
            self.window().add_recipient()
            row = self.rowCount() - 1
        event.acceptProposedAction()
        self.window().append_attachments_to_row(row, paths)


class ImportDialog(QDialog):
    """Dialog zum Import von Empfängern aus CSV/Excel:
    Spalten des Quellfiles per Dropdown auf Name/Anrede/E-Mail zuordnen."""

    FIELD_LABELS = [("name", "Name"), ("anrede", "Anrede"), ("email", "E-Mail")]

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Empfänger importieren – Spalten zuordnen")
        self.resize(720, 430)
        self.all_rows = [list(row) for row in rows]

        layout = QVBoxLayout(self)

        self.header_check = QCheckBox("Erste Zeile enthält Spaltenüberschriften")
        self.header_check.setChecked(True)
        self.header_check.stateChanged.connect(self.refresh)
        layout.addWidget(self.header_check)

        mapping_layout = QHBoxLayout()
        mapping_layout.addWidget(QLabel("Spalten zuordnen:"))
        self.combos = {}
        for field, label in self.FIELD_LABELS:
            mapping_layout.addWidget(QLabel(f"{label}:"))
            combo = QComboBox()
            combo.addItem("(keine Zuordnung)", None)
            self.combos[field] = combo
            mapping_layout.addWidget(combo)
        layout.addLayout(mapping_layout)

        layout.addWidget(QLabel("Vorschau (erste 10 Zeilen):"))
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.preview)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self.refresh()

    def _source_width(self):
        return max((len(row) for row in self.all_rows), default=0)

    def _headers(self):
        width = self._source_width()
        if self.header_check.isChecked() and self.all_rows:
            return [str(v) for v in self.all_rows[0]] + [""] * (width - len(self.all_rows[0]))
        return [""] * width

    def refresh(self):
        headers = self._headers()

        for combo in self.combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(keine Zuordnung)", None)
            for idx, header in enumerate(headers):
                title = header.strip() if header.strip() else f"Spalte {idx + 1}"
                combo.addItem(f"Spalte {idx + 1}: {title}", idx)
            combo.blockSignals(False)

        # Automatische Zuordnung anhand von Überschriften-Mustern
        guessed = {}
        for idx, header in enumerate(headers):
            text = (header or "").strip().lower()
            if "name" in text and "name" not in guessed:
                guessed["name"] = idx
            elif text in ("anrede", "geschlecht", "herr", "frau") and "anrede" not in guessed:
                guessed["anrede"] = idx
            elif "mail" in text and "email" not in guessed:
                guessed["email"] = idx
        for field, _ in self.FIELD_LABELS:
            combo = self.combos[field]
            position = combo.findData(guessed.get(field))
            combo.setCurrentIndex(position if position >= 0 else 0)

        # Vorschau füllen
        preview_rows = self.all_rows[1:11] if self.header_check.isChecked() else self.all_rows[:10]
        width = self._source_width()
        self.preview.clear()
        self.preview.setColumnCount(width)
        self.preview.setRowCount(len(preview_rows))
        if self.header_check.isChecked():
            self.preview.setHorizontalHeaderLabels(headers)
        else:
            self.preview.setHorizontalHeaderLabels([f"Spalte {i + 1}" for i in range(width)])
        for r, row in enumerate(preview_rows):
            for c in range(width):
                self.preview.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))

    def _mapped_index(self, field):
        return self.combos[field].currentData()

    def _cell(self, row, field):
        idx = self._mapped_index(field)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    def get_recipients(self):
        start = 1 if self.header_check.isChecked() else 0
        return [(
            self._cell(row, "name"),
            self._cell(row, "anrede"),
            self._cell(row, "email")
        ) for row in self.all_rows[start:]]

    def accept(self):
        if self._mapped_index("email") is None:
            QMessageBox.warning(self, "Fehler", "Bitte wählen Sie eine Spalte für das E-Mail-Feld aus.")
            return
        super().accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serien-E-Mail Versand")
        self.setGeometry(100, 100, 950, 700)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.create_smtp_section()
        self.create_email_content_section()
        self.create_recipient_table()
        self.create_send_section()

        self.load_settings()
        self.load_recipients()

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def create_smtp_section(self):
        smtp_group = QWidget()
        smtp_layout = QHBoxLayout(smtp_group)

        smtp_layout.addWidget(QLabel("Absender-E-Mail:"))
        self.smtp_user = QLineEdit()
        smtp_layout.addWidget(self.smtp_user)

        smtp_layout.addWidget(QLabel("SMTP-Server:"))
        self.smtp_server = QLineEdit("smtp.example.com")
        smtp_layout.addWidget(self.smtp_server)

        smtp_layout.addWidget(QLabel("Port:"))
        self.smtp_port = QLineEdit("587")
        smtp_layout.addWidget(self.smtp_port)

        smtp_layout.addWidget(QLabel("Passwort:"))
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.Password)
        smtp_layout.addWidget(self.smtp_password)

        # BCC-Option hinzufügen
        self.bcc_check = QCheckBox("BCC an Absender")
        smtp_layout.addWidget(self.bcc_check)

        smtp_layout.addWidget(QLabel(""))
        save_settings_btn = QPushButton("Einstellungen speichern unter...")
        save_settings_btn.clicked.connect(self.save_settings_as)
        smtp_layout.addWidget(save_settings_btn)

        load_settings_btn = QPushButton("Einstellungen laden aus...")
        load_settings_btn.clicked.connect(self.load_settings_from)
        smtp_layout.addWidget(load_settings_btn)

        self.layout.addWidget(smtp_group)

    def create_email_content_section(self):
        content_group = QWidget()
        content_layout = QVBoxLayout(content_group)

        subject_layout = QHBoxLayout()
        subject_layout.addWidget(QLabel("Betreff:"))
        self.email_subject = QLineEdit()
        subject_layout.addWidget(self.email_subject)
        content_layout.addLayout(subject_layout)

        content_layout.addWidget(QLabel("E-Mail Text (mit {Name} oder {Anrede} Platzhalter):"))
        self.email_body = QTextEdit()
        self.email_body.setAcceptRichText(False)
        content_layout.addWidget(self.email_body)

        draft_button_layout = QHBoxLayout()
        save_draft_btn = QPushButton("Text als Entwurf speichern...")
        save_draft_btn.clicked.connect(self.save_draft_as)
        draft_button_layout.addWidget(save_draft_btn)

        load_draft_btn = QPushButton("Entwurf laden...")
        load_draft_btn.clicked.connect(self.load_draft_from)
        draft_button_layout.addWidget(load_draft_btn)

        content_layout.addLayout(draft_button_layout)

        self.layout.addWidget(content_group)

    def create_recipient_table(self):
        self.recipient_table = RecipientTable()
        self.recipient_table.setHorizontalHeaderLabels(["", "Name", "Anrede", "E-Mail", "Anhang-Pfad(e)", ""])
        # Spalten manuell per Ziehen der Trennlinie anpassbar; zusätzliche
        # Fensterbreite geht ausschließlich an "Anhang-Pfad(e)" (Stretch)
        header = self.recipient_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.recipient_table.setColumnWidth(0, 30)
        self.recipient_table.setColumnWidth(1, 150)
        self.recipient_table.setColumnWidth(2, 90)
        self.recipient_table.setColumnWidth(3, 220)
        self.recipient_table.setColumnWidth(5, 160)
        self.recipient_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed
        )
        self.recipient_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recipient_table.customContextMenuRequested.connect(self.show_context_menu)
        # Doppelklick auf die Anhang-Spalte öffnet den Anhang-Dialog
        self.recipient_table.cellDoubleClicked.connect(self.table_double_clicked)

        button_group = QWidget()
        button_layout = QHBoxLayout(button_group)

        add_button = QPushButton("Empfänger hinzufügen")
        add_button.clicked.connect(self.add_recipient)
        button_layout.addWidget(add_button)

        import_button = QPushButton("Empfänger importieren (CSV/Excel)...")
        import_button.clicked.connect(self.import_recipients_from_file)
        button_layout.addWidget(import_button)

        save_button = QPushButton("Empfängerliste speichern unter...")
        save_button.clicked.connect(self.save_recipients_as)
        button_layout.addWidget(save_button)

        load_button = QPushButton("Empfängerliste laden aus...")
        load_button.clicked.connect(self.load_recipients_from)
        button_layout.addWidget(load_button)

        table_group = QWidget()
        table_layout = QVBoxLayout(table_group)
        table_layout.addWidget(button_group)
        table_layout.addWidget(self.recipient_table)
        self.layout.addWidget(table_group)

    def show_context_menu(self, pos):
        menu = QMenu()
        delete_action = menu.addAction("Empfänger löschen")
        action = menu.exec_(self.recipient_table.viewport().mapToGlobal(pos))
        if action == delete_action:
            row = self.recipient_table.rowAt(pos.y())
            if row >= 0:
                self.delete_recipient(row)

    def create_send_section(self):
        send_group = QWidget()
        send_layout = QHBoxLayout(send_group)

        self.progress_label = QLabel("Bereit zum Versand")
        send_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        send_layout.addWidget(self.progress_bar)

        self.send_button = QPushButton("Serien-Mails versenden")
        self.send_button.clicked.connect(self.send_emails)
        send_layout.addWidget(self.send_button)

        self.layout.addWidget(send_group)

    def add_recipient(self):
        row_position = self.recipient_table.rowCount()
        self.recipient_table.insertRow(row_position)

        delete_btn = QPushButton("✕")
        delete_btn.setStyleSheet("background-color: #ff4444; color: white; border: none; font-weight: bold;")
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda _, r=row_position: self.delete_recipient(r))
        self.recipient_table.setCellWidget(row_position, 0, delete_btn)

        self.recipient_table.setItem(row_position, 1, QTableWidgetItem(""))

        anrede_combo = QComboBox()
        anrede_combo.addItems(["Herr", "Frau"])
        self.recipient_table.setCellWidget(row_position, 2, anrede_combo)

        self.recipient_table.setItem(row_position, 3, QTableWidgetItem(""))

        self.recipient_table.setItem(row_position, 4, QTableWidgetItem(""))

        attach_btn = QPushButton("Dateien hinzufügen...")
        attach_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        attach_btn.clicked.connect(lambda _, r=row_position: self.add_attachments(r))
        self.recipient_table.setCellWidget(row_position, 5, attach_btn)

    def delete_recipient(self, row):
        self.recipient_table.removeRow(row)

    def table_double_clicked(self, row, column):
        if column == 4:
            self.open_attachment_dialog(row)

    def _get_row_attachments(self, row):
        item = self.recipient_table.item(row, 4)
        text = item.text() if item else ""
        return [p.strip() for p in text.split(";") if p.strip()]

    def _set_row_attachments(self, row, paths):
        item = self.recipient_table.item(row, 4)
        if item is None:
            item = QTableWidgetItem()
            self.recipient_table.setItem(row, 4, item)
        item.setText("; ".join(paths))

    def open_attachment_dialog(self, row):
        dialog = AttachmentDialog(self._get_row_attachments(row), self)
        if dialog.exec_() == QDialog.Accepted:
            self._set_row_attachments(row, dialog.get_paths())

    def append_attachments_to_row(self, row, paths):
        file_paths = self._get_row_attachments(row)
        for path in paths:
            if path not in file_paths:
                file_paths.append(path)
        self._set_row_attachments(row, file_paths)

    def add_attachments(self, row):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Dateien auswählen", "", "Alle Dateien (*)"
        )
        if paths:
            self.append_attachments_to_row(row, paths)

    def import_recipients_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Empfänger importieren", "",
            "Tabellen (*.csv *.txt *.xlsx);;CSV/Text (*.csv *.txt);;Excel (*.xlsx)"
        )
        if not path:
            return

        rows = self._load_table_file(path)
        if rows is None:
            return  # Fehler wurde bereits gemeldet
        # Komplett leere Zeilen herausfiltern
        rows = [row for row in rows if any(str(cell).strip() for cell in row)]
        if not rows:
            QMessageBox.warning(self, "Fehler", "Die Datei enthält keine verwertbaren Zeilen.")
            return

        dialog = ImportDialog(rows, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        imported = 0
        for name, anrede, email in dialog.get_recipients():
            if not name and not email:
                continue
            self.add_recipient()
            row = self.recipient_table.rowCount() - 1
            self.recipient_table.item(row, 1).setText(name)
            anrede_combo = self.recipient_table.cellWidget(row, 2)
            if anrede_combo:
                position = anrede_combo.findText(anrede)
                anrede_combo.setCurrentIndex(position if position >= 0 else 0)
            self.recipient_table.item(row, 3).setText(email)
            imported += 1

        if imported:
            QMessageBox.information(self, "Erfolg", f"{imported} Empfänger wurden importiert.")
        else:
            QMessageBox.warning(self, "Hinweis", "Es wurden keine Empfänger importiert.")

    def _load_table_file(self, path):
        """Liest CSV (nativ) oder Excel (openpyxl, falls installiert)
        und gibt eine Matrix aus geparsten Zeilen zurück."""
        lower = path.lower()
        if lower.endswith((".xlsx", ".xls")):
            try:
                from openpyxl import load_workbook
            except ImportError:
                QMessageBox.warning(
                    self, "Fehler",
                    "Für Excel-Dateien wird das Paket 'openpyxl' benötigt:\n\n"
                    "python -m pip install openpyxl\n\n"
                    "Alternativ die Tabelle als CSV speichern und importieren."
                )
                return None
            try:
                workbook = load_workbook(path, read_only=True, data_only=True)
                sheet = workbook.active
                data = [
                    [("" if cell is None else str(cell).strip()) for cell in row]
                    for row in sheet.iter_rows(values_only=True)
                ]
                workbook.close()
                return data
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Datei konnte nicht gelesen werden:\n{str(e)}")
                return None

        # CSV/Text: Trennzeichen anhand der ersten Zeile erraten
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                first_line = f.readline()
                f.seek(0)
                delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
                return [row for row in csv.reader(f, delimiter=delimiter)]
        except UnicodeDecodeError:
            pass
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Datei konnte nicht gelesen werden:\n{str(e)}")
            return None
        # Fallback: andere Kodierung (z. B. von älterem Excel gespeicherte CSVs)
        try:
            with open(path, "r", encoding="latin-1", newline="") as f:
                first_line = f.readline()
                f.seek(0)
                delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
                return [row for row in csv.reader(f, delimiter=delimiter)]
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Datei konnte nicht gelesen werden:\n{str(e)}")
            return None

    def save_settings(self):
        self._save_settings_to_path(SETTINGS_FILE)

    def _save_settings_to_path(self, path):
        settings = {
            "smtp_user": self.smtp_user.text().strip(),
            "smtp_server": self.smtp_server.text().strip(),
            "smtp_port": self.smtp_port.text().strip(),
            "smtp_password": self.smtp_password.text(),
            "bcc_enabled": self.bcc_check.isChecked()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def save_settings_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Einstellungen speichern", SETTINGS_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            self._save_settings_to_path(path)
            QMessageBox.information(self, "Erfolg", f"Einstellungen wurden nach\n{path}\ngespeichert.")

    def load_settings(self):
        self._load_settings_from_path(SETTINGS_FILE)

    def _load_settings_from_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            self.smtp_user.setText(settings.get("smtp_user", ""))
            self.smtp_server.setText(settings.get("smtp_server", "smtp.example.com"))
            self.smtp_port.setText(settings.get("smtp_port", "587"))
            self.smtp_password.setText(settings.get("smtp_password", ""))
            self.bcc_check.setChecked(settings.get("bcc_enabled", False))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def load_settings_from(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Einstellungen laden", SETTINGS_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            try:
                self._load_settings_from_path(path)
                QMessageBox.information(self, "Erfolg", f"Einstellungen wurden aus\n{path}\ngeladen.")
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Fehler beim Laden:\n{str(e)}")

    def save_draft_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Entwurf speichern", DRAFT_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            self._save_draft_to_path(path)
            QMessageBox.information(self, "Erfolg", f"Entwurf wurde nach\n{path}\ngespeichert.")

    def _save_draft_to_path(self, path):
        draft = {
            "subject": self.email_subject.text(),
            "body": self.email_body.toPlainText()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)

    def load_draft_from(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Entwurf laden", DRAFT_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            try:
                self._load_draft_from_path(path)
                QMessageBox.information(self, "Erfolg", f"Entwurf wurde aus\n{path}\ngeladen.")
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Fehler beim Laden:\n{str(e)}")

    def _load_draft_from_path(self, path):
        with open(path, "r", encoding="utf-8") as f:
            draft = json.load(f)
        self.email_subject.setText(draft.get("subject", ""))
        self.email_body.setPlainText(draft.get("body", ""))

    def save_recipients(self):
        self._save_recipients_to_path(RECIPIENTS_FILE)

    def _save_recipients_to_path(self, path):
        recipients = []
        for row in range(self.recipient_table.rowCount()):
            name_item = self.recipient_table.item(row, 1)
            anrede_combo = self.recipient_table.cellWidget(row, 2)
            email_item = self.recipient_table.item(row, 3)
            attachment_item = self.recipient_table.item(row, 4)

            name = name_item.text().strip() if name_item else ""
            anrede = anrede_combo.currentText() if anrede_combo else "Herr"
            email = email_item.text().strip() if email_item else ""
            attachments = attachment_item.text().strip() if attachment_item else ""

            recipients.append({
                "name": name,
                "anrede": anrede,
                "email": email,
                "attachments": attachments
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(recipients, f, indent=2, ensure_ascii=False)

    def save_recipients_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Empfängerliste speichern", RECIPIENTS_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            self._save_recipients_to_path(path)
            QMessageBox.information(self, "Erfolg", f"Empfängerliste wurde nach\n{path}\ngespeichert.")

    def load_recipients(self):
        self._load_recipients_from_path(RECIPIENTS_FILE)

    def _load_recipients_from_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                recipients = json.load(f)

            self.recipient_table.setRowCount(0)
            for recipient in recipients:
                self.add_recipient()
                row = self.recipient_table.rowCount() - 1

                self.recipient_table.item(row, 1).setText(recipient.get("name", ""))
                anrede_combo = self.recipient_table.cellWidget(row, 2)
                if anrede_combo:
                    anrede_combo.setCurrentText(recipient.get("anrede", "Herr"))
                self.recipient_table.item(row, 3).setText(recipient.get("email", ""))
                self.recipient_table.item(row, 4).setText(recipient.get("attachments", ""))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def load_recipients_from(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Empfängerliste laden", RECIPIENTS_FILE, "JSON-Dateien (*.json)"
        )
        if path:
            try:
                self._load_recipients_from_path(path)
                QMessageBox.information(self, "Erfolg", f"Empfängerliste wurde aus\n{path}\ngeladen.")
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Fehler beim Laden:\n{str(e)}")

    def send_emails(self):
        server = self.smtp_server.text().strip()
        port_str = self.smtp_port.text().strip()
        sender_email = self.smtp_user.text().strip()
        password = self.smtp_password.text()
        subject = self.email_subject.text().strip()
        body_template = self.email_body.toPlainText()
        bcc_enabled = self.bcc_check.isChecked()

        if not server or not port_str:
            QMessageBox.warning(self, "Fehler", "SMTP-Server und Port müssen angegeben werden.")
            return

        if not sender_email:
            QMessageBox.warning(self, "Fehler", "Absender-E-Mail ist erforderlich für den Versand.")
            return

        try:
            port = int(port_str)
        except ValueError:
            QMessageBox.warning(self, "Fehler", "Port muss eine Zahl sein.")
            return

        recipients = []
        for row in range(self.recipient_table.rowCount()):
            name_item = self.recipient_table.item(row, 1)
            anrede_combo = self.recipient_table.cellWidget(row, 2)
            email_item = self.recipient_table.item(row, 3)
            attachment_item = self.recipient_table.item(row, 4)

            name = name_item.text().strip() if name_item else ""
            anrede = anrede_combo.currentText() if anrede_combo else "Herr"
            email = email_item.text().strip() if email_item else ""
            attachment_paths_str = attachment_item.text().strip() if attachment_item else ""

            attachment_paths = [p.strip() for p in attachment_paths_str.split(";") if p.strip()]
            valid_attachments = [p for p in attachment_paths if os.path.isfile(p)]

            if email and valid_attachments:
                recipients.append((name, anrede, email, valid_attachments))

        if not recipients:
            QMessageBox.warning(self, "Fehler", "Keine gültigen Empfänger zum Versand gefunden.")
            return

        # Anhangsumfang prüfen: Warnung, wenn eine Mail über der Provider-Grenze liegt
        limit_bytes = ATTACHMENT_SIZE_WARNING_MB * 1024 * 1024
        oversized = []
        for name, anrede, email, attachment_paths in recipients:
            size = sum(os.path.getsize(p) for p in attachment_paths)
            if size > limit_bytes:
                recipient_label = f"{'“' + name + '” ' if name else ''}<{email}>"
                oversized.append(
                    f"{recipient_label}: {size / (1024 * 1024):.1f} MB"
                )
        if oversized:
            answer = QMessageBox.question(
                self, "Große Anhänge",
                f"Mindestens eine Mail übersteigt die {ATTACHMENT_SIZE_WARNING_MB}-MB-Grenze:\n\n"
                + "\n".join(oversized)
                + "\n\nDer SMTP-Server könnte die Zustellung verweigern.\nTrotzdem versenden?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                return

        total = len(recipients)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.send_button.setEnabled(False)
        QApplication.processEvents()

        try:
            with smtplib.SMTP(server, port) as smtp:
                smtp.starttls()
                if sender_email and password:
                    smtp.login(sender_email, password)

                for i, (name, anrede, email, attachment_paths) in enumerate(recipients, 1):
                    self.progress_label.setText(f"Versende E-Mail {i} von {total} an {email}...")
                    QApplication.processEvents()

                    msg = MIMEMultipart()
                    msg['From'] = sender_email
                    msg['To'] = email
                    msg['Subject'] = subject

                    # BCC hinzufügen, falls aktiviert
                    if bcc_enabled:
                        msg['Bcc'] = sender_email

                    body = body_template.replace("{Name}", name)
                    if "{Anrede}" in body:
                        full_anrede = f"Sehr geehrter Herr {name}" if anrede == "Herr" else f"Sehr geehrte Frau {name}"
                        body = body.replace("{Anrede}", full_anrede)

                    msg.attach(MIMEText(body, 'plain'))

                    for attachment_path in attachment_paths:
                        # MIME-Typ anhand der Dateiendung ermitteln, Fallback: octet-stream
                        mime_type, _ = mimetypes.guess_type(attachment_path)
                        if not mime_type:
                            mime_type = 'application/octet-stream'

                        with open(attachment_path, 'rb') as f:
                            part = MIMEBase(*mime_type.split('/'))
                            part.set_payload(f.read())
                        encoders.encode_base64(part)

                        # Dateinamen bereinigen und korrekt kodieren
                        filename = os.path.basename(attachment_path)
                        safe_filename = "".join(c for c in filename if c.isalnum() or c in ('-', '_', '.', ' ')).strip()
                        if not safe_filename:
                            safe_filename = "attachment"

                        # RFC 2231-konforme Kodierung für den Dateinamen
                        # (add_header kodiert Umlaute automatisch korrekt)
                        part.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename=safe_filename
                        )
                        msg.attach(part)

                    smtp.send_message(msg)
                    time.sleep(1)

                    self.progress_bar.setValue(i)
                    QApplication.processEvents()

            QMessageBox.information(self, "Erfolg", f"Alle {total} E-Mails wurden erfolgreich versendet!")
        except smtplib.SMTPAuthenticationError:
            QMessageBox.critical(self, "Fehler", "SMTP-Authentifizierung fehlgeschlagen. Bitte überprüfen Sie E-Mail und Passwort.")
        except smtplib.SMTPException as e:
            QMessageBox.critical(self, "Fehler", f"SMTP-Fehler: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Versand: {str(e)}")
        finally:
            self.send_button.setEnabled(True)
            self.progress_bar.setValue(0)
            self.progress_label.setText("Bereit zum Versand")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
