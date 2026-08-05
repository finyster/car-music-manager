# GUI 安裝

```powershell
Set-Location "C:\Projects\car-music-manager"
git fetch origin
git switch feat/gui-mvp
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\car-music-gui.exe
```

第一次安裝 PySide6 可能需要一些時間。程式仍需要 `ffmpeg` 與 `ffprobe` 位於 PATH。
