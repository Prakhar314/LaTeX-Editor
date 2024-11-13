import sys
import os
import subprocess
import tempfile
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QTextEdit, QLabel, QPushButton, 
                            QFileDialog, QMessageBox, QSplitter, QTabWidget)
from PyQt6.QtCore import Qt, QProcess, QUrl, QRegularExpression
from PyQt6.QtGui import (QAction, QTextCursor, QSyntaxHighlighter, 
                        QTextCharFormat, QColor, QFont)
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Command format (e.g., \begin, \end, \section, etc.)
        command_format = QTextCharFormat()
        command_format.setForeground(QColor("#C94922"))  # Dark red
        command_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append(
            (QRegularExpression(r'\\[a-zA-Z]+'), command_format)
        )

        # Environment format (content between \begin{} and \end{})
        environment_format = QTextCharFormat()
        environment_format.setForeground(QColor("#2C5288"))  # Dark blue
        self.highlighting_rules.append(
            (QRegularExpression(r'\\(begin|end)\{[^}]*\}'), environment_format)
        )

        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#37A437"))  # Dark green
        self.highlighting_rules.append(
            (QRegularExpression(r'%.*'), comment_format)
        )

        # Math format (inline)
        math_format = QTextCharFormat()
        math_format.setForeground(QColor("#9B2393"))  # Purple
        self.highlighting_rules.append(
            (QRegularExpression(r'\$[^$]*\$'), math_format)
        )

        # Math format (display)
        self.highlighting_rules.append(
            (QRegularExpression(r'\\\[[^\]]*\\\]'), math_format)
        )

        # Curly braces format
        braces_format = QTextCharFormat()
        braces_format.setForeground(QColor("#676767"))  # Gray
        braces_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append(
            (QRegularExpression(r'[\{\}]'), braces_format)
        )

        # Square brackets format
        brackets_format = QTextCharFormat()
        brackets_format.setForeground(QColor("#676767"))  # Gray
        self.highlighting_rules.append(
            (QRegularExpression(r'[\[\]]'), brackets_format)
        )

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            matches = pattern.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

class LatexEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.temp_dir = None
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.initUI()

    def initUI(self):
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create main splitter
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Create horizontal splitter for editor and preview
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Create text editor with monospace font
        self.editor = QTextEdit()
        font = QFont("Courier New", 12)
        self.editor.setFont(font)
        self.editor.setPlaceholderText("Enter your LaTeX code here...")
        
        # Apply syntax highlighting
        self.highlighter = LatexHighlighter(self.editor.document())
        
        h_splitter.addWidget(self.editor)

        # Create menu bar
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')

        new_action = QAction('&New', self)
        new_action.setShortcut('Ctrl+N')
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction('&Open...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction('&Save', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        save_as_action = QAction('Save &As...', self)
        save_as_action.setShortcut('Ctrl+Shift+S')
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)
        
        # Edit menu
        edit_menu = menubar.addMenu('&Edit')
        
        self.undo_action = QAction('&Undo', self)
        self.undo_action.setShortcut('Ctrl+Z')
        self.undo_action.triggered.connect(self.editor.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        
        self.redo_action = QAction('&Redo', self)
        self.redo_action.setShortcuts(['Ctrl+Shift+Z', 'Ctrl+Y'])
        self.redo_action.triggered.connect(self.editor.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        
        edit_menu.addSeparator()
        
        cut_action = QAction('Cu&t', self)
        cut_action.setShortcut('Ctrl+X')
        cut_action.triggered.connect(self.editor.cut)
        edit_menu.addAction(cut_action)
        
        copy_action = QAction('&Copy', self)
        copy_action.setShortcut('Ctrl+C')
        copy_action.triggered.connect(self.editor.copy)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction('&Paste', self)
        paste_action.setShortcut('Ctrl+V')
        paste_action.triggered.connect(self.editor.paste)
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        select_all_action = QAction('Select &All', self)
        select_all_action.setShortcut('Ctrl+A')
        select_all_action.triggered.connect(self.editor.selectAll)
        edit_menu.addAction(select_all_action)

        # Set up undo/redo stack
        self.editor.document().modificationChanged.connect(self.handle_modification)
        self.editor.undoAvailable.connect(self.undo_action.setEnabled)
        self.editor.redoAvailable.connect(self.redo_action.setEnabled)

        # Create preview area
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        # Add PDF viewer with proper initialization
        self.pdf_viewer = QWebEngineView()
        self.pdf_viewer.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        self.pdf_viewer.settings().setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, True)
        
        # Set a minimum size for the PDF viewer
        self.pdf_viewer.setMinimumSize(400, 400)
        
        # Add a placeholder message
        self.pdf_viewer.setHtml("""
            <html>
                <body style="display: flex; justify-content: center; align-items: center; height: 100%; margin: 0; background-color: #f0f0f0;">
                    <div style="text-align: center; color: #666;">
                        <h2>PDF Preview</h2>
                        <p>Compile your LaTeX document to see the preview here</p>
                    </div>
                </body>
            </html>
        """)
        
        preview_layout.addWidget(self.pdf_viewer)
        
        compile_button = QPushButton("Compile")
        compile_button.clicked.connect(self.compile_latex)
        preview_layout.addWidget(compile_button)
        
        h_splitter.addWidget(preview_widget)
        
        # Set the horizontal split ratio (50:50)
        h_splitter.setSizes([600, 600])
        
        main_splitter.addWidget(h_splitter)
        
        # Add compilation log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("Compilation log will appear here...")
        main_splitter.addWidget(self.log_text)
        
        # Set the vertical split ratio
        main_splitter.setSizes([600, 100])
        
        layout.addWidget(main_splitter)

        # Set window properties
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowTitle('LaTeX Editor')
        self.show()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.log_text.append(data)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.log_text.append(data)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def new_file(self):
        if self.editor.toPlainText():
            reply = QMessageBox.question(self, 'New File',
                'Do you want to save the current file?',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Yes:
                self.save_file()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.editor.clear()
        self.current_file = None
        self.setWindowTitle('LaTeX Editor')
        self.log_text.clear()

    def open_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open file', '',
            'LaTeX files (*.tex);;All files (*.*)')

        if fname:
            try:
                with open(fname, 'r') as f:
                    self.editor.setText(f.read())
                self.current_file = fname
                self.setWindowTitle(f'LaTeX Editor - {fname}')
                self.log_text.clear()
                
                # Check if there's a corresponding PDF and display it
                pdf_file = os.path.splitext(fname)[0] + '.pdf'
                if os.path.exists(pdf_file):
                    self.display_pdf(pdf_file)
            except Exception as e:
                QMessageBox.critical(self, 'Error',
                    f'Could not open file: {str(e)}')

    def save_file(self):
        if not self.current_file:
            return self.save_file_as()

        try:
            with open(self.current_file, 'w') as f:
                f.write(self.editor.toPlainText())
            self.editor.document().setModified(False)
            self.setWindowTitle(f'LaTeX Editor - {self.current_file}')
            return True
        except Exception as e:
            QMessageBox.critical(self, 'Error',
                f'Could not save file: {str(e)}')
            return False

    def save_file_as(self):
        """Save the current file with a new name"""
        fname, _ = QFileDialog.getSaveFileName(self, 'Save file', '',
            'LaTeX files (*.tex);;All files (*.*)')
        if fname:
            self.current_file = fname
            self.save_file()

    def display_pdf(self, pdf_path):
        if os.path.exists(pdf_path):
            # Convert the file path to URL format
            url = QUrl.fromLocalFile(os.path.abspath(pdf_path))
            self.pdf_viewer.setUrl(url)
            
            # Add a small delay to ensure the PDF is loaded
            QApplication.processEvents()

    def cleanup_temp(self):
        """Clean up temporary files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            for file in os.listdir(self.temp_dir):
                try:
                    os.remove(os.path.join(self.temp_dir, file))
                except:
                    pass
            try:
                os.rmdir(self.temp_dir)
            except:
                pass
            self.temp_dir = None

    def create_temp_file(self):
        """Create a temporary file with the current content"""
        if not self.temp_dir:
            self.temp_dir = tempfile.mkdtemp()
        
        temp_tex = os.path.join(self.temp_dir, "temp.tex")
        with open(temp_tex, 'w') as f:
            f.write(self.editor.toPlainText())
        return temp_tex

    def compile_latex(self):
        # Clear previous log
        self.log_text.clear()

        # If we have a saved file, save the current content
        if self.current_file:
            self.save_file()
            tex_file = self.current_file
            working_dir = os.path.dirname(self.current_file)
        else:
            # Create a temporary file for compilation
            tex_file = self.create_temp_file()
            working_dir = self.temp_dir
        
        # Set up the process
        self.process.setWorkingDirectory(working_dir)
        
        # Run pdflatex with additional options for better output
        self.process.start('pdflatex', [
            '-interaction=nonstopmode',
            '-file-line-error',
            '-halt-on-error',
            tex_file
        ])
        
        # Wait for the process to finish
        self.process.waitForFinished()
        
        if self.process.exitCode() == 0:
            # Display the generated PDF
            pdf_file = os.path.splitext(tex_file)[0] + '.pdf'
            self.display_pdf(pdf_file)
        else:
            self.log_text.append("Compilation failed. Check the log for details.")

    def closeEvent(self, event):
        """Clean up temporary files when closing the application"""
        self.cleanup_temp()
        super().closeEvent(event)

    def handle_modification(self, changed):
        """Handle document modification"""
        if self.current_file:
            self.setWindowTitle(f"{'*' if changed else ''}LaTeX Editor - {self.current_file}")
        else:
            self.setWindowTitle(f"{'*' if changed else ''}LaTeX Editor - Untitled")

def main():
    app = QApplication(sys.argv)
    ex = LatexEditor()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
