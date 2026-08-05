"""YouTube Music enhanced desktop interface."""

from __future__ import annotations

import sys
from dataclasses import replace

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .gui import GuiTrack, MainWindow, parse_batch_urls, split_artist_title
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


class YTMusicMainWindow(MainWindow):
    """Main window with a dedicated YouTube Music metadata workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Car Music Manager — YouTube Music")
        self.ytmusic_loader: YTMusicMetadataLoader | None = None
        self._install_ytmusic_controls()

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
        note = QLabel("YT Music 專用：只讀取曲目資料；遠端音訊仍需勾選『有權取得』。")
        note.setWordWrap(True)
        row.addWidget(button)
        row.addWidget(note, 1)
        layout.addLayout(row)
        self.url_input.setPlaceholderText(
            "每行貼上一個 YouTube、YouTube Music、播放清單或頻道網址。\n"
            "一般網址按『讀取網址』；music.youtube.com 網址按『讀取 YouTube Music』。"
        )

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
        error_messages = list(errors)  # type: ignore[arg-type]
        self.status_label.setText(
            f"YouTube Music 已加入 {len(source_entries)} 首；錯誤 {len(error_messages)}"
        )
        if error_messages:
            QMessageBox.warning(self, "部分 YouTube Music 來源讀取失敗", "\n".join(error_messages[:10]))

    def add_track(self, track: GuiTrack) -> None:
        if track.source_type != "YT Music":
            super().add_track(track)
            return
        row = self.table.rowCount()
        super().add_track(replace(track, source_type="YouTube"))
        self.table.item(row, self.COL_TYPE).setText("YT Music")
        source_info = track.uploader.strip()
        self.table.item(row, self.COL_SOURCE_INFO).setText(
            f"YouTube Music｜{source_info}" if source_info else "YouTube Music"
        )

    def _selected_jobs(self) -> list[dict[str, object]]:
        jobs = super()._selected_jobs()
        for job in jobs:
            row = int(job["row"])
            source_type = self.table.item(row, self.COL_TYPE).text()
            if source_type == "YT Music":
                job["source_type"] = "YouTube"
        return jobs


def main() -> int:
    """Launch the YouTube Music enhanced desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("Car Music Manager")
    window = YTMusicMainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
