# GUI 快速測試

此介面保留原本的安全轉檔核心，只增加 Windows 操作畫面。

## 安裝或更新

```powershell
Set-Location "C:\Projects\car-music-manager"
git fetch origin
git switch feat/gui-mvp
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

確認 FFmpeg 可用：

```powershell
ffmpeg -version
ffprobe -version
```

## 啟動

```powershell
.\.venv\Scripts\car-music-gui.exe
```

也可以使用：

```powershell
.\.venv\Scripts\python.exe -m car_music_manager.gui
```

## 最快測試流程

1. 按「加入本機音樂」選一至三首音訊，或在網址框每行貼上一個影片、播放清單或頻道網址後按「讀取網址」。
2. 在表格勾選要處理的歌曲，直接修改歌手、歌名、專輯。
3. 遠端來源只有在你確實有權取得時，才勾選「有權取得」。版本正確不等於下載授權。
4. 按「選擇目的地」選擇隨身碟或資料夾；按「新增資料夾」可在目前目的地下建立子資料夾。
5. 專輯圖片為選配，可選 JPG、PNG 或 WEBP；輸出會轉成最大 500×500 的 JPEG 並嵌入 ID3v2.3。
6. 按「開始處理已勾選歌曲」。單首失敗不會中止其他歌曲。

預設輸出 Profile：MP3 256 kbps CBR、44.1 kHz、Stereo、-16 LUFS、True Peak -1.5 dBTP、ID3v2.3。

## 驗證

完成後執行：

```powershell
.\.venv\Scripts\car-music.exe verify "D:\你的輸出資料夾"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## MVP 限制

- 這一版使用一張共用封面套用到本次選取的歌曲；後續可增加逐首封面。
- 遠端清單先讀取 metadata。只有使用者勾選「有權取得」的來源才會進入現有 authorized download 流程。
- 暫停功能尚未加入；可取消，並會在目前單曲處理結束後停止下一首。
