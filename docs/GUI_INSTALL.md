# GUI 安裝

```powershell
Set-Location "C:\Projects\car-music-manager"
git fetch origin
git switch feat/gui-mvp
git pull origin feat/gui-mvp
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\car-music-gui.exe
```

第一次安裝 PySide6 可能需要一些時間。程式仍需要 `ffmpeg` 與 `ffprobe` 位於 PATH。

目前 GUI 版本為 0.5.0，包含 YouTube Music 讀取、自動封面與跨次執行的重複歌曲過濾。
