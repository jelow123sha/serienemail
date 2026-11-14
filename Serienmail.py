import sys
import time
import os
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
    QTableWidgetItem, QProgressBar, QMessageBox, QHeaderView, QComboBox, QFileDialog, QMenu, QCheckBox
)
from PyQt5.QtCore import Qt

SETTINGS_FILE = "einstellungen.json"
RECIPIENTS_FILE = "empfaenger.json"

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

        self.layout.addWidget(content_group)

    def create_recipient_table(self):
        self.recipient_table = QTableWidget(0, 6)
        self.recipient_table.setHorizontalHeaderLabels(["", "Name", "Anrede", "E-Mail", "Anhang-Pfad(e)", ""])
        self.recipient_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.recipient_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed
        )
        self.recipient_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recipient_table.customContextMenuRequested.connect(self.show_context_menu)

        button_group = QWidget()
        button_layout = QHBoxLayout(button_group)

        add_button = QPushButton("Empfänger hinzufügen")
        add_button.clicked.connect(self.add_recipient)
        button_layout.addWidget(add_button)

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

    def add_attachments(self, row):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Dateien auswählen", "", "Alle Dateien (*)"
        )
        if paths:
            current_item = self.recipient_table.item(row, 4)
            current_text = current_item.text() if current_item else ""

            file_paths = []
            if current_text:
                file_paths = [p.strip() for p in current_text.split(";") if p.strip()]

            for path in paths:
                if path not in file_paths:
                    file_paths.append(path)

            if file_paths:
                current_item.setText("; ".join(file_paths))

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
