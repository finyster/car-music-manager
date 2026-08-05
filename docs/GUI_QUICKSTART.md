# GUI 快速測試

此介面保留原本的安全轉檔核心，並增加 Windows GUI、YouTube Music、逐首封面與重複過濾。

## 安裝或更新

```powershell
Set-Location "C:\Projects\car-music-manager"
git fetch origin
git switch feat/gui-mvp
git pull origin feat/gui-mvp
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
.\.venv\Scripts\python.exe -m car_music_manager.gui_ytmusic
```

## 最快測試流程

1. 貼上 YouTube Music 網址後按「讀取 YouTube Music」，或加入一至三首本機音訊。
2. 保持「自動抓取每首封面」與「自動略過重複歌曲」勾選。
3. 在表格勾選要處理的歌曲，並修改歌手、歌名、專輯。
4. 遠端來源只有在確實有權取得時，才勾選「有權取得」。
5. 選擇目的資料夾；手動共用封面為選配，而且會優先於自動封面。
6. 按「開始處理已勾選歌曲」。單首失敗不會中止其他歌曲。

預設輸出 Profile：MP3 256 kbps CBR、44.1 kHz、Stereo、-16 LUFS、True Peak -1.5 dBTP、ID3v2.3、封面 500×500 JPEG。

## 重複測試

將同一首影片分別以以下網址形式載入：

```text
https://music.youtube.com/watch?v=VIDEO_ID
https://www.youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
```

預期只加入一筆，狀態列顯示其餘來源已略過。成功處理後再次處理同一來源，狀態應顯示「重複略過」，目的資料夾中不會新增 `(2).mp3`。

目的資料夾會新增：

```text
.car-music-dedupe.json
```

這是跨次執行使用的去重索引，不是音樂檔。需要刻意保留 Live、Remix 或不同演奏版本時，可以取消「自動略過重複歌曲」。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\car-music.exe verify "D:\你的輸出資料夾"
```

## 目前限制

- 去重使用 YouTube ID、來源、嚴格歌手／歌名、來源檔 SHA-256 與目的地索引，不是聲學指紋。
- 不同編碼但聲音相同、同時網址和標籤也不同時，可能仍需人工確認。
- 暫停功能尚未加入；取消會在目前單曲處理結束後停止下一首。
