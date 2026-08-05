"""YouTube Music enhanced desktop interface with automatic artwork support."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)

from .artwork import download_artwork
from .gui import GuiTrack, MainWindow, parse_batch_urls, split_artist_title
from .models import ProcessingOptions, TagData
from .process import process_one
from .tags import embed_artwork, embed_artwork_jpeg
from .youtube import download_authorized
from .ytmusic import YTMusicEntry, is_ytmusic_url, list_ytmusic


class YTMusicMetadataLoader(QThread):
    """Load one or more YouTube Music links without blocking the GUI."""

    loaded = Signal(object, object)

    def __init__(self, urls: list[str]) -> None:
        super().__init__()
        self.urls = urls

    def run(self) -> None:  # noqa: D102
        entries: list[YTMusicEntry] = []
        errors: list[str] = []
        for url in self.urls:
            try:
                entries.extend(list_ytmusic(url))
            except Exception as error:  # Qt worker boundary: show concise per-URL errors
                errors.append(f"{url}: {error}")
        self.loaded.emit(entries, errors)


class ArtworkProcessingWorker(QThread):
    """Process selected audio and add manual or per-track YouTube Music artwork."""

    progress = Signal(int, int, str)
    row_finished = Signal(int, str, str)
    artwork_finished = Signal(int, str, str)
    completed = Signal(int, int, int)

    def __init__(
        self,
        jobs: list[dict[str, object]],
        destination: Path,
        manual_artwork: Path | None,
    ) -> None:
        super().__init__()
        self.jobs = jobs
        self.destination = destination
        self.manual_artwork = manual_artwork

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
                            self.artwork_finished.emit(row, "略過", "音訊來源尚未確認授權")
                            continue
                        source_path = download_authorized(
                            source_value,
                            temporary_root / f"remote-{row}",
                        )
                    else:
                        source_path = Path(source_value)
                        if not source_path.exists():
                            raise FileNotFoundError(source_path)

                    artwork_source = "manual" if self.manual_artwork else str(
                        job.get("artwork_source") or "none"
                    )
                    tags = TagData(
                        title=title,
                        artist=str(job["artist"]) or None,
                        album=str(job["album"]) or None,
                        album_artist=str(job["artist"]) or None,
                        track_number=str(job["track_number"]),
                        comment=(
                            "Prepared by car-music-manager GUI; "
                            f"cover_source={artwork_source}"
                        ),
                    )
                    output = process_one(
                        source_path,
                        self.destination,
                        options=options,
                        tags=tags,
                        output_stem=str(job["output_stem"]),
                    )

                    artwork_warning = ""
                    try:
                        if self.manual_artwork:
                            embed_artwork(output, self.manual_artwork, max_size=500)
                            self.artwork_finished.emit(row, "手動封面", str(self.manual_artwork))
                        else:
                            artwork_url = str(job.get("artwork_url") or "").strip()
                            if artwork_url:
                                downloaded = download_artwork(
                                    artwork_url,
                                    temporary_root / f"artwork-{row}.jpg",
                                    max_size=500,
                                )
                                embed_artwork_jpeg(output, downloaded.read_bytes())
                                self.artwork_finished.emit(row, "已自動嵌入", artwork_url)
                            else:
                                self.artwork_finished.emit(row, "無封面", "來源沒有可用圖片")
                    except Exception as artwork_error:
                        artwork_warning = f"封面處理失敗：{artwork_error}"
                        self.artwork_finished.emit(row, "封面失敗", artwork_warning)

                    completed += 1
                    if artwork_warning:
                        self.row_finished.emit(
                            row,
                            "完成（封面警告）",
                            f"{output}\n{artwork_warning}",
                        )
                    else:
                        self.row_finished.emit(row, "完成", str(output))
                except Exception as error:  # Batch boundary: continue with remaining rows
                    failed += 1
                    self.row_finished.emit(row, "失敗", str(error))
                    self.artwork_finished.emit(row, "未處理", str(error))
        self.completed.emit(completed, skipped, failed)


class YTMusicMainWindow(MainWindow):
    """Main window with dedicated YouTube Music metadata and artwork workflows."""

    COL_ARTWORK = 10

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Car Music Manager — YouTube Music")
        self.ytmusic_loader: YTMusicMetadataLoader | None = None
        self.ytmusic_artwork_urls: dict[int, str] = {}
        self._install_artwork_column()
        self._install_ytmusic_controls()

    def _install_artwork_column(self) -> None:
        self.table.setColumnCount(self.COL_ARTWORK + 1)
        self.table.setHorizontalHeaderItem(self.COL_ARTWORK, QTableWidgetItem("封面"))
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_ARTWORK,
            QHeaderView.ResizeMode.ResizeToContents,
        )

    def _install_ytmusic_controls(self) -> None:
        source_group = next(
            (
                group
                for group in self.findChildren(QGroupBox)
                if group.title().startswith("1. 加入來源")
            ),
            None,
        )
        if source_group is None:
            return
        layout = source_group.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        row = QHBoxLayout()
        button = QPushButton("讀取 YouTube Music")
        button.setToolTip("支援 YouTube Music 歌曲、播放清單、專輯與藝人頻道網址")
        button.clicked.connect(self.load_ytmusic_urls)
        self.auto_artwork_checkbox = QCheckBox("自動抓取每首封面")
        self.auto_artwork_checkbox.setChecked(
            str(self.settings.value("auto_ytmusic_artwork", "true")).casefold()
            not in {"false", "0", "no"}
        )
        self.auto_artwork_checkbox.setToolTip(
            "處理歌曲時下載該曲目的 YouTube Music 圖片，轉成 500×500 JPEG 後嵌入 MP3。"
        )
        note = QLabel("讀取只抓 Metadata；封面在處理時才下載，失敗不影響音訊輸出。")
        note.setWordWrap(True)
        row.addWidget(button)
        row.addWidget(self.auto_artwork_checkbox)
        row.addWidget(note, 1)
        layout.addLayout(row)
        self.url_input.setPlaceholderText(
            "每行貼上一個 YouTube、YouTube Music、播放清單或頻道網址。\n"
            "一般網址按『讀取網址』；music.youtube.com 網址按『讀取 YouTube Music』。"
        )

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if hasattr(self, "auto_artwork_checkbox"):
            self.settings.setValue(
                "auto_ytmusic_artwork",
                self.auto_artwork_checkbox.isChecked(),
            )
        super().closeEvent(event)

    def load_ytmusic_urls(self) -> None:
        urls = parse_batch_urls(self.url_input.toPlainText())
        if not urls:
            QMessageBox.information(self, "沒有網址", "請先貼上一個或多個 YouTube Music 網址。")
            return
        invalid = [url for url in urls if not is_ytmusic_url(url)]
        valid = [url for url in urls if is_ytmusic_url(url)]
        if invalid:
            QMessageBox.warning(
                self,
                "略過非 YouTube Music 網址",
                "以下網址不是 music.youtube.com，請改用『讀取網址』：\n\n"
                + "\n".join(invalid[:10]),
            )
        if not valid:
            return
        if self.ytmusic_loader and self.ytmusic_loader.isRunning():
            return
        self.status_label.setText("正在讀取 YouTube Music 曲目資料…")
        self.ytmusic_loader = YTMusicMetadataLoader(valid)
        self.ytmusic_loader.loaded.connect(self._ytmusic_metadata_loaded)
        self.ytmusic_loader.start()

    def _ytmusic_metadata_loaded(self, entries: object, errors: object) -> None:
        source_entries = list(entries)  # type: ignore[arg-type]
        for entry in source_entries:
            artist = entry.artist.strip()
            title = entry.title.strip()
            if not artist:
                artist, title = split_artist_title(title, entry.uploader)
            row = self.table.rowCount()
            self.add_track(
                GuiTrack(
                    source=entry.source,
                    source_type="YT Music",
                    title=title,
                    artist=artist,
                    album=entry.album,
                    duration_seconds=entry.duration_seconds,
                    uploader=entry.uploader,
                )
            )
            artwork_url = entry.thumbnail_url.strip()
            if artwork_url:
                self.ytmusic_artwork_urls[row] = artwork_url
                self.table.item(row, self.COL_ARTWORK).setText("可自動抓取")
                self.table.item(row, self.COL_ARTWORK).setToolTip(artwork_url)
            else:
                self.table.item(row, self.COL_ARTWORK).setText("來源無圖片")

        error_messages = list(errors)  # type: ignore[arg-type]
        artwork_count = sum(
            1 for row in range(self.table.rowCount()) if row in self.ytmusic_artwork_urls
        )
        self.status_label.setText(
            f"YouTube Music 已加入 {len(source_entries)} 首；"
            f"可抓封面 {artwork_count}；錯誤 {len(error_messages)}"
        )
        if error_messages:
            QMessageBox.warning(self, "部分 YouTube Music 來源讀取失敗", "\n".join(error_messages[:10]))

    def add_track(self, track: GuiTrack) -> None:
        row = self.table.rowCount()
        if track.source_type == "YT Music":
            super().add_track(replace(track, source_type="YouTube"))
            self.table.item(row, self.COL_TYPE).setText("YT Music")
            source_info = track.uploader.strip()
            self.table.item(row, self.COL_SOURCE_INFO).setText(
                f"YouTube Music｜{source_info}" if source_info else "YouTube Music"
            )
        else:
            super().add_track(track)
        self.table.setItem(row, self.COL_ARTWORK, QTableWidgetItem("無"))

    def _selected_jobs(self) -> list[dict[str, object]]:
        jobs = super()._selected_jobs()
        auto_artwork = self.auto_artwork_checkbox.isChecked()
        for job in jobs:
            row = int(job["row"])
            source_type = self.table.item(row, self.COL_TYPE).text()
            if source_type == "YT Music":
                job["source_type"] = "YouTube"
                if auto_artwork:
                    job["artwork_url"] = self.ytmusic_artwork_urls.get(row, "")
                    job["artwork_source"] = "ytmusic_thumbnail"
        return jobs

    def start_processing(self) -> None:
        jobs = self._selected_jobs()
        if not jobs:
            QMessageBox.information(self, "沒有選取歌曲", "請至少勾選一首歌曲。")
            return
        destination_text = self.destination_input.text().strip()
        if not destination_text:
            QMessageBox.information(self, "沒有目的地", "請先選擇輸出目的資料夾。")
            return
        destination = Path(destination_text)
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
        self.processor = ArtworkProcessingWorker(jobs, destination, self.artwork_path)
        self.processor.progress.connect(self._processing_progress)
        self.processor.row_finished.connect(self._row_finished)
        self.processor.artwork_finished.connect(self._artwork_finished)
        self.processor.completed.connect(self._processing_completed)
        self.processor.start()

    def _artwork_finished(self, row: int, status: str, message: str) -> None:
        item = self.table.item(row, self.COL_ARTWORK)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, self.COL_ARTWORK, item)
        item.setText(status)
        item.setToolTip(message)


def main() -> int:
    """Launch the YouTube Music enhanced desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("Car Music Manager")
    window = YTMusicMainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
