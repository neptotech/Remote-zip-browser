import sys
import os
import shutil
from PyQt6.QtWidgets import (
    QApplication, QTreeView, QMainWindow, 
    QFileIconProvider, QPushButton, QVBoxLayout, QWidget,
    QMessageBox, QLineEdit, QFileDialog, QHBoxLayout, QProgressBar, QLabel
)
from PyQt6.QtCore import Qt, QModelIndex, QAbstractItemModel, QThread, QObject, pyqtSignal
from remotezip import RemoteZip
import urllib.request

icon_provider = QFileIconProvider()
def detect_remote_filetype(url):
    """Detect file type by reading the first few bytes of the remote file."""
    try:
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-7'})
        with urllib.request.urlopen(req) as resp:
            sig = resp.read(8)
        # ZIP: 50 4B 03 04 or 50 4B 05 06 or 50 4B 07 08
        if sig.startswith(b'PK\x03\x04') or sig.startswith(b'PK\x05\x06') or sig.startswith(b'PK\x07\x08'):
            return "zip"
        # 7z: 37 7A BC AF 27 1C
        if sig.startswith(b'7z\xbc\xaf\x27\x1c'):
            return "7z"
        return "other"
    except Exception:
        return "error"
# --------------------------
# Tree Node
# --------------------------
class Node:
    def __init__(self, name, is_dir=False, parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = []
        self.zipinfo = None

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def get_path_parts(self):
        """Return list of path components from root (excluding ROOT)."""
        parts = []
        node = self
        while node and node.parent:
            if node.parent.name != "ROOT":
                parts.insert(0, node.parent.name)
            node = node.parent
        return parts


# --------------------------
# Model
# --------------------------
class RemoteZipModel(QAbstractItemModel):
    def __init__(self, zip_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zip_url = zip_url
        self.root = Node("ROOT", is_dir=True)

        with RemoteZip(zip_url) as rz:
            for info in rz.infolist():
                parts = info.filename.strip("/").split("/")
                current = self.root

                for i, part in enumerate(parts):
                    is_last = (i == len(parts) - 1)
                    is_dir = info.is_dir() if is_last else True

                    child = next((c for c in current.children if c.name == part), None)
                    if not child:
                        child = Node(part, is_dir=is_dir)
                        current.add_child(child)

                    current = child

                if not current.is_dir:
                    current.zipinfo = info

    def rowCount(self, parent):
        node = parent.internalPointer() if parent.isValid() else self.root
        return len(node.children)

    def columnCount(self, parent):
        return 1

    def data(self, index, role):
        if not index.isValid():
            return None
        node = index.internalPointer()

        if role == Qt.ItemDataRole.DisplayRole:
            return node.name

        if role == Qt.ItemDataRole.DecorationRole:
            if node.is_dir:
                return icon_provider.icon(QFileIconProvider.IconType.Folder)
            else:
                from PyQt6.QtCore import QFileInfo
                return icon_provider.icon(QFileInfo(node.name))
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = parent.internalPointer() if parent.isValid() else self.root
        child = parent_node.children[row]
        return self.createIndex(row, column, child)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if node.parent is None or node.parent == self.root:
            return QModelIndex()
        grandparent = node.parent.parent
        row = grandparent.children.index(node.parent) if grandparent else 0
        return self.createIndex(row, 0, node.parent)

    def get_node(self, index):
        return index.internalPointer() if index.isValid() else None


# --------------------------
# Worker (runs in background thread)
# --------------------------
class ExtractWorker(QObject):
    file_progress = pyqtSignal(str, int, int)    # filename, current, total (per-file)
    overall_progress = pyqtSignal(int, int) # downloaded, total
    finished = pyqtSignal()

    def __init__(self, zip_url, nodes, dest_dir):
        super().__init__()
        self.zip_url = zip_url
        self.nodes = nodes
        self.dest_dir = dest_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.nodes = self.nodes
        self.dest_dir = self.dest_dir

    def run(self):
        # collect all files under the selected nodes
        files_to_extract = []
        def collect_files(node):
            if node.is_dir:
                for child in node.children:
                    collect_files(child)
            else:
                files_to_extract.append(node)

        for node in self.nodes:
            collect_files(node)

        # compute total size
        total_size = sum(n.zipinfo.file_size for n in files_to_extract)
        downloaded_size = 0

        with RemoteZip(self.zip_url) as rz:
            for node in files_to_extract:
                if self._cancelled:
                    self.finished.emit()
                    return
                rel_parts = node.get_path_parts() + [node.name]
                target_path = os.path.join(self.dest_dir, *rel_parts)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                # download in chunks with progress
                with rz.open(node.zipinfo) as src, open(target_path, "wb") as dst:
                    read = 0
                    chunk_size = 64 * 1024
                    while True:
                        if self._cancelled:
                            self.finished.emit()
                            return
                        buf = src.read(chunk_size)
                        if not buf:
                            break
                        dst.write(buf)
                        read += len(buf)
                        self.file_progress.emit(node.name, read, node.zipinfo.file_size)

                        downloaded_size += len(buf)
                        self.overall_progress.emit(downloaded_size, total_size)

        self.finished.emit()



# --------------------------
# Custom TreeView
# --------------------------
class CustomTree(QTreeView):
    def __init__(self, model, zip_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setModel(model)
        self.zip_url = zip_url
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)


# --------------------------
# Main App
# --------------------------
def main():
    import tempfile
    import subprocess

    app = QApplication(sys.argv)
    window = QMainWindow()


    central = QWidget()
    layout = QVBoxLayout(central)

    # Only show this label on home screen
    placeholder_label = QLabel("No zip loaded. Use the toolbar to open a remote zip URL.")
    placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center the text
    layout.addWidget(placeholder_label, alignment=Qt.AlignmentFlag.AlignCenter)  # Center the widget

    # Container for all zip-related controls, hidden on home screen
    zip_controls = QWidget()
    zip_layout = QVBoxLayout(zip_controls)
    zip_controls.setVisible(False)
    layout.addWidget(zip_controls)

    tree = None  # Will be created after URL is opened

    # Toolbar/Menu
    from PyQt6.QtWidgets import QToolBar
    from PyQt6.QtGui import QAction
    toolbar = QToolBar()
    window.addToolBar(toolbar)
    open_url_action = QAction("Open URL", window)
    about_action = QAction("About", window)  # Add About action
    toolbar.addAction(open_url_action)
    toolbar.addAction(about_action)  # Add About to toolbar

    def open_zip_url():
        from PyQt6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(window, "Open Remote Zip", "Enter Zip URL:")
        if ok and url:
            nonlocal tree
            # --- Detect file type before opening ---
            filetype = detect_remote_filetype(url)
            if filetype == "zip":
                pass  # continue as normal
            elif filetype == "7z":
                QMessageBox.information(window, "7z Archive Detected", "This is a 7z archive. 7z is not supported.")
                return
            elif filetype == "other":
                QMessageBox.warning(window, "Unsupported Format", "This file is not a ZIP or 7z archive. Unsupported format.")
                return
            elif filetype == "error":
                QMessageBox.warning(window, "Error", "Could not read the file signature from the URL.")
                return
            # --- Continue with ZIP logic ---
            try:
                model = RemoteZipModel(url)
            except Exception as e:
                QMessageBox.critical(window, "Error", f"Failed to open zip:\n{e}")
                return
            if tree:
                zip_layout.removeWidget(tree)
                tree.deleteLater()
            tree = CustomTree(model, url)
            tree.setHeaderHidden(True)
            zip_layout.insertWidget(0, tree)
            tree.doubleClicked.connect(on_tree_double_clicked)
            placeholder_label.setVisible(False)
            zip_controls.setVisible(True)

    open_url_action.triggered.connect(open_zip_url)

    # About dialog logic
    def show_about():
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        dlg = QDialog(window)
        dlg.setWindowTitle("About RemoteZip Explorer")
        layout = QVBoxLayout(dlg)
        about_label = QLabel(
            "<b>RemoteZip Explorer</b><br>"
            "Version 1.0<br><br>"
            "A simple tool to browse and extract remote ZIP files.<br><br>"
            "Developed by Vishnu(aka redoc).<br>"
            "Github: <a href='https://github.com/neptotech/'>redoc</a><br><br>"
            "© 2025"
        )
        about_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_label.setTextFormat(Qt.TextFormat.RichText)
        about_label.setOpenExternalLinks(True)
        layout.addWidget(about_label)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignCenter)
        dlg.setLayout(layout)
        dlg.exec()

    about_action.triggered.connect(show_about)

    def on_tree_double_clicked(index):

        if not tree:
            return
        node = tree.model().get_node(index)
        if node is None or node.is_dir:
            return
        # Download the file to a temp directory
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, node.name)
        # Avoid overwriting if file exists, add a suffix
        base, ext = os.path.splitext(file_path)
        count = 1
        while os.path.exists(file_path):
            file_path = f"{base}_{count}{ext}"
            count += 1
        # Download the file
        with RemoteZip(tree.zip_url) as rz:
            with rz.open(node.zipinfo) as src, open(file_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        # Open the file with the default application
        try:
            if sys.platform.startswith("win"):
                os.startfile(file_path)
            elif sys.platform.startswith("darwin"):
                subprocess.run(["open", file_path], check=False)
            else:
                subprocess.run(["xdg-open", file_path], check=False)
        except Exception as e:
            QMessageBox.warning(window, "Open File", f"Failed to open file:\n{file_path}\n{e}")




    # Path selector (inside zip_controls)
    path_layout = QHBoxLayout()
    path_edit = QLineEdit()
    btn_browse = QPushButton("Browse…")
    path_layout.addWidget(path_edit)
    path_layout.addWidget(btn_browse)
    zip_layout.addLayout(path_layout)

    def browse_dir():
        d = QFileDialog.getExistingDirectory(window, "Select Extract Directory")
        if d:
            path_edit.setText(d)

    btn_browse.clicked.connect(browse_dir)

    # Progress bars (inside zip_controls)
    lbl_file = QLabel("Current file: None")
    pb_file = QProgressBar()
    lbl_overall = QLabel("Overall progress:")
    pb_overall = QProgressBar()
    zip_layout.addWidget(lbl_file)
    zip_layout.addWidget(pb_file)
    zip_layout.addWidget(lbl_overall)
    zip_layout.addWidget(pb_overall)

    # Extract, Cancel, and Bare Zip buttons in a horizontal layout (inside zip_controls)
    btn_extract = QPushButton("Extract Selection")
    btn_cancel = QPushButton("Cancel")
    btn_cancel.setEnabled(False)
    btn_bare = QPushButton("Download Bare Zip")
    from PyQt6.QtWidgets import QSizePolicy
    for btn in (btn_extract, btn_cancel, btn_bare):
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    btns_layout = QHBoxLayout()
    btns_layout.addWidget(btn_extract)
    btns_layout.addWidget(btn_cancel)
    btns_layout.addWidget(btn_bare)
    btns_layout.setSpacing(20)
    zip_layout.addLayout(btns_layout)

    # Use mutable containers to allow assignment in nested functions
    state = {'thread': None, 'worker': None}

    def on_extract():
        if not tree:
            QMessageBox.warning(window, "No zip loaded", "Please open a zip URL first.")
            return
        selected_indexes = tree.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(window, "No selection", "Please select some files/folders.")
            return
        dest_dir = path_edit.text().strip()
        if not dest_dir:
            QMessageBox.warning(window, "No directory", "Please choose a destination directory.")
            return
        nodes = [tree.model().get_node(idx) for idx in selected_indexes if idx.column() == 0]

        # keep references to avoid premature GC
        thread = QThread()
        worker = ExtractWorker(tree.zip_url, nodes, dest_dir)
        state['thread'] = thread
        state['worker'] = worker
        worker.moveToThread(thread)
        btn_cancel.setEnabled(True)
        btn_extract.setEnabled(False)

        worker.file_progress.connect(
            lambda fname, cur, total: (
                lbl_file.setText(f"Current file: {fname}"),
                pb_file.setValue(int(cur * 100 / total) if total else 0)
            )
        )
        worker.overall_progress.connect(
            lambda cur, total: pb_overall.setValue(int(cur * 100 / total) if total else 0)
        )

        def cleanup():
            btn_cancel.setEnabled(False)
            btn_extract.setEnabled(True)
            QMessageBox.information(window, "Done", f"Extraction finished into:\n{dest_dir}")
            thread.quit()
            thread.wait()
            worker.deleteLater()
            thread.deleteLater()
            state['thread'] = None
            state['worker'] = None

        worker.finished.connect(cleanup)
        thread.started.connect(worker.run)
        thread.start()


    btn_extract.clicked.connect(on_extract)


    def on_cancel():
        if state['worker']:
            state['worker'].cancel()
        btn_cancel.setEnabled(False)

    btn_cancel.clicked.connect(on_cancel)

    # --- Bare Zip logic ---
    import zipfile


    def on_bare_zip():

        if not tree:
            QMessageBox.warning(window, "No zip loaded", "Please open a zip URL first.")
            return
        dest_dir = path_edit.text().strip()
        if not dest_dir:
            QMessageBox.warning(window, "No directory", "Please choose a destination directory.")
            return

        # choose save location
        save_path, _ = QFileDialog.getSaveFileName(window, "Save Bare Zip", os.path.join(dest_dir, "bare_structure.zip"), "Zip Files (*.zip)")
        if not save_path:
            return

        # Create bare zip
        model = tree.model()
        with zipfile.ZipFile(save_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            def add_node(node, base_parts):
                path = "/".join(base_parts + [node.name])
                if node.is_dir:
                    # add directory entry
                    if not path.endswith("/"):
                        path += "/"
                    zf.writestr(path, b"")  
                    for child in node.children:
                        add_node(child, base_parts + [node.name])
                else:
                    # add file entry but with empty content
                    zf.writestr(path, b"")

            for child in model.root.children:
                add_node(child, [])

        QMessageBox.information(window, "Bare Zip Created", f"Bare zip saved at:\n{save_path}")

    btn_bare.clicked.connect(on_bare_zip)

    btn_cancel.clicked.connect(on_cancel)


    window.setCentralWidget(central)
    window.resize(900, 650)
    window.setWindowTitle("RemoteZip Explorer")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



