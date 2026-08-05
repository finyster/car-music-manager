"""PySide6 desktop interface for car-music-manager.

The GUI intentionally reuses the existing safe processing functions. Remote
sources are listed as metadata first and are only downloaded when the user
explicitly confirms that they have permission to do so.
"""

from __future__ import annotations

import csv
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .files import discover_audio, sanitize_filename
from .models import ProcessingOptions, TagData
from .process import process_one
from .tags import embed_artwork
from .youtube import SourceEntry, download_authorized, list_youtube


@dataclass(frozen=True)
class GuiTrack:
    """One selectable source shown in the desktop table."""

    source: str
    source_type: str
    title: str
    artist: str = ""
    album: str = ""
    duration_seconds: int | None = None
    uploader: str = ""
    rights_confirmed: bool = False


def parse_batch_urls(text: str) -> list[str]:
    """Return unique non-empty URL lines while preserving input order."""
    seen: set[str] = set()
    urls: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line in seen:
            continue
        seen.add(line)
        urls.append(line)
    return urls


def split_artist_title(video_title: str, uploader: str | None = None) -> tuple[str, str]:
    """Best-effort split used only to prefill editable GUI cells."""
    cleaned = video_title.strip()
    for separator in (" - ", "－", "–", "—"):
        if separator in cleaned:
            artist, title = cleaned.split(separator, 1)
            if artist.strip() and title.strip():
                return artist.strip(), title.strip()
    return (uploader or "").strip(), cleaned


def output_stem(index: int, artist: str, title: str) -> str:
    """Build a deterministic Windows-safe car filename stem."""
    label = f"{index:02d} - {artist.strip() or '未知歌手'} - {title.strip() or '未命名'}"
    return sanitize_filename(label)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    minutes, remaining = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remaining:02d}" if hours else f"{minutes}:{remaining:02d}"


class MetadataLoader(QThread):
    """Load remote metadata without blocking the Qt event loop."""

    loaded = Signal(object, object)

    def __init__(self, urls: list[str]) -> None:
        super().__init__()
        self.urls = urls

    def run(self) -> None:  # noqa: D102
        entries: list[SourceEntry] = []
        errors: list[str] = []
        for url in self.urls:
            try:
                entries.extend(list_youtube(url))
            except Exception as error:  # Qt worker boundary: convert to user-facing text
                errors.append(f"{url}: {error}")
        self.loaded.emit(entries, errors)


class ProcessingWorker(QThread):
    """Process selected rows sequentially so one failure does not stop the batch."""

    progress = Signal(int, int, str)
    row_finished = Signal(int, str, str)
    completed = Signal(int, int, int)

    def __init__(
        self,
        jobs: list[dict[str, object]],
        destination: Path,
        artwork: Path | None,
    ) -> None:
        super().__init__()
        self.jobs = jobs
        self.destination = destination
        self.artwork = artwork

    def run(self) -> None:  # noqa: D102
        completed = 0
        skipped = 0
        failed = 0
        options = ProcessingOptions()
        self.destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="car-music-gui-") as temporary_directory:
            temporary_root = Path(temporary_directory)
            total = len(self.jobs)
            for position, job in enumerate(self.jobs, start=1):
                if self.isInterruptionRequested():
                    break
                row = int(job["row"])
                title = str(job["title"])
                self.progress.emit(position, total, title)
                try:
                    source_type = str(job["source_type"])
                    source_value = str(job["source"])
                    if source_type == "YouTube":
                        if not bool(job["rights_confirmed"]):
                            skipped += 1
                            self.row_finished.emit(row, "待授權", "未勾選來源授權確認")
                            continue
                        source_path = download_authorized(source_value, temporary_root / f"remote-{row}")
                    else:
                        source_path = Path(source_value)
                        if not source_path.exists():
                            raise FileNotFoundError(source_path)

                    tags = TagData(
                        title=title,
                        artist=str(job["artist"]) or None,
                        album=str(job["album"]) or None,
                        album_artist=str(job["artist"]) or None,
                        track_number=str(job["track_number"]),
                        comment="Prepared by car-music-manager GUI",
                    )
                    output = process_one(
                        source_path,
                        self.destination,
                        options=options,
                        tags=tags,
                        output_stem=str(job["output_stem"]),
                    )
                    if self.artwork:
                        embed_artwork(output, self.artwork, max_size=500)
                    completed += 1
                    self.row_finished.emit(row, "完成", str(output))
                except Exception as error:  # Batch boundary: continue with remaining rows
                    failed += 1
                    self.row_finished.emit(row, "失敗", str(error))
        self.completed.emit(completed, skipped, failed)


class MainWindow(QMainWindow):
    """Compact MVP desktop workflow for loading, selecting and processing tracks."""

    COL_SELECTED = 0
    COL_TYPE = 1
    COL_ARTIST = 2
    COL_TITLE = 3
    COL_ALBUM = 4
    COL_DURATION = 5
    COL_SOURCE_INFO = 6
    COL_RIGHTS = 7
    COL_STATUS = 8
    COL_SOURCE = 9

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Car Music Manager")
        self.resize(1180, 760)
        self.settings = QSettings("car-music-manager", "desktop")
        self.loader: MetadataLoader | None = None
        self.processor: ProcessingWorker | None = None
        self.artwork_path: Path | None = None
        self._build_ui()
        self._restore_settings()

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)

        source_group = QGroupBox("1. 加入來源")
        source_layout = QVBoxLayout(source_group)
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "每行貼上一個影片、播放清單或頻道網址。只會先讀取曲目資料。"
        )
        self.url_input.setMaximumHeight(100)
        source_layout.addWidget(self.url_input)
        source_buttons = QHBoxLayout()
        load_button = QPushButton("讀取網址")
        load_button.clicked.connect(self.load_urls)
        import_button = QPushButton("匯入 TXT / CSV")
        import_button.clicked.connect(self.import_links_file)
        local_button = QPushButton("加入本機音樂")
        local_button.clicked.connect(self.add_local_files)
        folder_button = QPushButton("加入本機資料夾")
        folder_button.clicked.connect(self.add_local_folder)
        for button in (load_button, import_button, local_button, folder_button):
            source_buttons.addWidget(button)
        source_buttons.addStretch(1)
        source_layout.addLayout(source_buttons)
        outer.addWidget(source_group)

        controls = QHBoxLayout()
        select_all = QPushButton("全選")
        select_all.clicked.connect(lambda: self.set_all_selected(True))
        select_none = QPushButton("全不選")
        select_none.clicked.connect(lambda: self.set_all_selected(False))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜尋歌手、歌名、頻道或來源")
        self.search_input.textChanged.connect(self.apply_filter)
        controls.addWidget(select_all)
        controls.addWidget(select_none)
        controls.addWidget(self.search_input, 1)
        outer.addLayout(controls)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["選取", "來源", "歌手", "歌名", "專輯", "長度", "頻道 / 檔案", "有權取得", "狀態", "來源值"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_SOURCE_INFO, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnHidden(self.COL_SOURCE, True)
        outer.addWidget(self.table, 1)

        options_group = QGroupBox("2. 輸出、封面與車機設定")
        options_layout = QGridLayout(options_group)
        self.destination_input = QLineEdit()
        browse_button = QPushButton("選擇目的地")
        browse_button.clicked.connect(self.choose_destination)
        new_folder_button = QPushButton("新增資料夾")
        new_folder_button.clicked.connect(self.create_destination_folder)
        options_layout.addWidget(QLabel("目的資料夾"), 0, 0)
        options_layout.addWidget(self.destination_input, 0, 1)
        options_layout.addWidget(browse_button, 0, 2)
        options_layout.addWidget(new_folder_button, 0, 3)

        self.artwork_input = QLineEdit()
        self.artwork_input.setReadOnly(True)
        artwork_button = QPushButton("選擇專輯圖片")
        artwork_button.clicked.connect(self.choose_artwork)
        clear_artwork = QPushButton("清除")
        clear_artwork.clicked.connect(self.clear_artwork)
        options_layout.addWidget(QLabel("共用封面（選配）"), 1, 0)
        options_layout.addWidget(self.artwork_input, 1, 1)
        options_layout.addWidget(artwork_button, 1, 2)
        options_layout.addWidget(clear_artwork, 1, 3)

        profile = QLabel(
            "Toyota Corolla Cross 保守相容：MP3 256 kbps CBR｜44.1 kHz｜Stereo｜"
            "-16 LUFS｜True Peak -1.5 dBTP｜ID3v2.3｜封面 JPEG 500×500"
        )
        profile.setWordWrap(True)
        options_layout.addWidget(QLabel("車機 Profile"), 2, 0)
        options_layout.addWidget(profile, 2, 1, 1, 3)
        outer.addWidget(options_group)

        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.status_label = QLabel("就緒")
        self.start_button = QPushButton("開始處理已勾選歌曲")
        self.start_button.clicked.connect(self.start_processing)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        bottom.addWidget(self.status_label)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.start_button)
        bottom.addWidget(self.cancel_button)
        outer.addLayout(bottom)

        self.setCentralWidget(central)

    def _restore_settings(self) -> None:
        destination = self.settings.value("destination", "D:/Music")
        self.destination_input.setText(str(destination))
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.processor and self.processor.isRunning():
            answer = QMessageBox.question(self, "仍在處理", "目前仍在處理歌曲，要取消並關閉嗎？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.processor.requestInterruption()
            self.processor.wait(3000)
        self.settings.setValue("destination", self.destination_input.text())
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()

    def _checkbox(self, checked: bool, *, enabled: bool = True) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setEnabled(enabled)
        return checkbox

    def add_track(self, track: GuiTrack) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, self.COL_SELECTED, self._checkbox(True))
        self.table.setItem(row, self.COL_TYPE, QTableWidgetItem(track.source_type))
        self.table.setItem(row, self.COL_ARTIST, QTableWidgetItem(track.artist))
        self.table.setItem(row, self.COL_TITLE, QTableWidgetItem(track.title))
        self.table.setItem(row, self.COL_ALBUM, QTableWidgetItem(track.album))
        self.table.setItem(row, self.COL_DURATION, QTableWidgetItem(format_duration(track.duration_seconds)))
        self.table.setItem(row, self.COL_SOURCE_INFO, QTableWidgetItem(track.uploader))
        rights_enabled = track.source_type == "YouTube"
        self.table.setCellWidget(
            row,
            self.COL_RIGHTS,
            self._checkbox(track.rights_confirmed or not rights_enabled, enabled=rights_enabled),
        )
        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem("待處理"))
        self.table.setItem(row, self.COL_SOURCE, QTableWidgetItem(track.source))

    def load_urls(self) -> None:
        urls = parse_batch_urls(self.url_input.toPlainText())
        if not urls:
            QMessageBox.information(self, "沒有網址", "請先貼上一個或多個網址。")
            return
        if self.loader and self.loader.isRunning():
            return
        self.status_label.setText("正在讀取曲目資料…")
        self.loader = MetadataLoader(urls)
        self.loader.loaded.connect(self._metadata_loaded)
        self.loader.start()

    def _metadata_loaded(self, entries: object, errors: object) -> None:
        source_entries = list(entries)  # type: ignore[arg-type]
        for entry in source_entries:
            artist, title = split_artist_title(entry.title, entry.uploader)
            self.add_track(
                GuiTrack(
                    source=entry.source,
                    source_type="YouTube",
                    title=title,
                    artist=artist,
                    duration_seconds=entry.duration_seconds,
                    uploader=entry.uploader or "",
                )
            )
        error_messages = list(errors)  # type: ignore[arg-type]
        self.status_label.setText(f"已加入 {len(source_entries)} 首；錯誤 {len(error_messages)}")
        if error_messages:
            QMessageBox.warning(self, "部分來源讀取失敗", "\n".join(error_messages[:10]))

    def import_links_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "匯入連結", "", "連結檔案 (*.txt *.csv);;所有檔案 (*)"
        )
        if not filename:
            return
        path = Path(filename)
        urls: list[str] = []
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    value = row.get("url") or row.get("source") or row.get("recommended_url")
                    if value:
                        urls.append(value.strip())
        else:
            urls = parse_batch_urls(path.read_text(encoding="utf-8-sig"))
        self.url_input.setPlainText("\n".join(urls))
        self.load_urls()

    def add_local_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "選擇音樂",
            "",
            "音訊 (*.mp3 *.m4a *.aac *.flac *.wav *.ogg);;所有檔案 (*)",
        )
        for filename in filenames:
            path = Path(filename)
            artist, title = split_artist_title(path.stem)
            self.add_track(
                GuiTrack(
                    source=str(path),
                    source_type="本機",
                    artist=artist,
                    title=title,
                    uploader=str(path.parent),
                    rights_confirmed=True,
                )
            )

    def add_local_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇音樂資料夾")
        if not folder:
            return
        try:
            files = discover_audio(Path(folder))
        except Exception as error:
            QMessageBox.critical(self, "掃描失敗", str(error))
            return
        for path in files:
            artist, title = split_artist_title(path.stem)
            self.add_track(
                GuiTrack(
                    source=str(path),
                    source_type="本機",
                    artist=artist,
                    title=title,
                    uploader=str(path.parent),
                    rights_confirmed=True,
                )
            )
        self.status_label.setText(f"已加入 {len(files)} 個本機檔案")

    def set_all_selected(self, selected: bool) -> None:
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, self.COL_SELECTED)
            if isinstance(checkbox, QCheckBox) and not self.table.isRowHidden(row):
                checkbox.setChecked(selected)

    def apply_filter(self, query: str) -> None:
        needle = query.strip().casefold()
        for row in range(self.table.rowCount()):
            haystack = " ".join(
                self.table.item(row, column).text()
                for column in (
                    self.COL_TYPE,
                    self.COL_ARTIST,
                    self.COL_TITLE,
                    self.COL_ALBUM,
                    self.COL_SOURCE_INFO,
                )
                if self.table.item(row, column)
            ).casefold()
            self.table.setRowHidden(row, bool(needle and needle not in haystack))

    def choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "選擇輸出目的地", self.destination_input.text() or "D:/"
        )
        if folder:
            self.destination_input.setText(folder)

    def create_destination_folder(self) -> None:
        root = Path(self.destination_input.text().strip() or "D:/")
        name, accepted = QInputDialog.getText(self, "新增資料夾", "資料夾名稱：")
        if not accepted or not name.strip():
            return
        destination = root / sanitize_filename(name.strip())
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            QMessageBox.information(self, "已存在", f"資料夾已存在：\n{destination}")
        except OSError as error:
            QMessageBox.critical(self, "無法建立資料夾", str(error))
            return
        self.destination_input.setText(str(destination))

    def choose_artwork(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "選擇專輯圖片", "", "圖片 (*.jpg *.jpeg *.png *.webp)"
        )
        if filename:
            self.artwork_path = Path(filename)
            self.artwork_input.setText(filename)

    def clear_artwork(self) -> None:
        self.artwork_path = None
        self.artwork_input.clear()

    def _selected_jobs(self) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        track_number = 1
        for row in range(self.table.rowCount()):
            selected = self.table.cellWidget(row, self.COL_SELECTED)
            if not isinstance(selected, QCheckBox) or not selected.isChecked():
                continue
            rights = self.table.cellWidget(row, self.COL_RIGHTS)
            artist = self.table.item(row, self.COL_ARTIST).text().strip()
            title = self.table.item(row, self.COL_TITLE).text().strip()
            album = self.table.item(row, self.COL_ALBUM).text().strip()
            jobs.append(
                {
                    "row": row,
                    "source_type": self.table.item(row, self.COL_TYPE).text(),
                    "source": self.table.item(row, self.COL_SOURCE).text(),
                    "artist": artist,
                    "title": title,
                    "album": album,
                    "rights_confirmed": isinstance(rights, QCheckBox) and rights.isChecked(),
                    "track_number": track_number,
                    "output_stem": output_stem(track_number, artist, title),
                }
            )
            track_number += 1
        return jobs

    def start_processing(self) -> None:
        jobs = self._selected_jobs()
        if not jobs:
            QMessageBox.information(self, "沒有選取歌曲", "請至少勾選一首歌曲。")
            return
        destination = Path(self.destination_input.text().strip())
        if not str(destination):
            QMessageBox.information(self, "沒有目的地", "請先選擇輸出目的資料夾。")
            return
        remote_unconfirmed = sum(
            1
            for job in jobs
            if job["source_type"] == "YouTube" and not job["rights_confirmed"]
        )
        if remote_unconfirmed:
            answer = QMessageBox.question(
                self,
                "部分遠端來源未確認授權",
                f"有 {remote_unconfirmed} 首未勾選『有權取得』，這些歌曲會跳過。仍要繼續嗎？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.processor = ProcessingWorker(jobs, destination, self.artwork_path)
        self.processor.progress.connect(self._processing_progress)
        self.processor.row_finished.connect(self._row_finished)
        self.processor.completed.connect(self._processing_completed)
        self.processor.start()

    def _processing_progress(self, current: int, total: int, title: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(current - 1)
        self.status_label.setText(f"處理中 {current}/{total}：{title}")

    def _row_finished(self, row: int, status: str, message: str) -> None:
        self.table.item(row, self.COL_STATUS).setText(status)
        self.table.item(row, self.COL_STATUS).setToolTip(message)
        self.progress.setValue(self.progress.value() + 1)

    def _processing_completed(self, completed: int, skipped: int, failed: int) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(f"完成 {completed}｜跳過 {skipped}｜失敗 {failed}")
        QMessageBox.information(
            self,
            "批次完成",
            f"完成：{completed}\n跳過：{skipped}\n失敗：{failed}\n\n輸出：{self.destination_input.text()}",
        )

    def cancel_processing(self) -> None:
        if self.processor and self.processor.isRunning():
            self.processor.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("正在安全停止…")


def main() -> int:
    """Launch the desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("Car Music Manager")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
