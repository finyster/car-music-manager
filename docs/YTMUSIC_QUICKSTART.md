# YouTube Music 專用讀取功能

此功能只讀取 `music.youtube.com` 的曲目資料，不會因為按下讀取按鈕就下載音訊。

## 啟動

```powershell
Set-Location "C:\Projects\car-music-manager"
git switch feat/gui-mvp
git pull origin feat/gui-mvp
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\car-music-gui.exe
```

## 使用方式

1. 從 YouTube Music 複製歌曲、播放清單、專輯或藝人頁面的網址。
2. 將網址貼到 GUI 上方輸入框；可一次貼多行。
3. 按 **讀取 YouTube Music**。
4. 程式會移除 `si` 等追蹤參數，並依序嘗試最合適的 metadata 入口。
5. 曲目會出現在表格，來源顯示為 **YT Music**。
6. 可直接修改歌手、歌名與專輯，並勾選需要的曲目。
7. 預設會自動略過重複來源與相同版本。
8. 保持 **自動抓取每首封面** 勾選，處理時會抓取圖片並嵌入 MP3。

支援的常見網址形式：

```text
https://music.youtube.com/watch?v=...
https://music.youtube.com/playlist?list=...
https://music.youtube.com/@artist
https://music.youtube.com/channel/...
```

對藝人網址，程式會優先嘗試相對穩定的普通 YouTube `/videos` metadata 頁，再退回藝人首頁及原始 YouTube Music URL。播放清單或專輯則優先保留 YouTube Music URL，失敗時再嘗試普通 YouTube 對應網址。

## Metadata 與封面

可讀取時，程式會優先使用 yt-dlp 回傳的：

- track / title
- artist / creator
- album
- duration
- uploader / channel
- thumbnail URL

表格會顯示歌手、歌名、專輯、長度、頻道與封面狀態。處理歌曲時，圖片會轉成 500×500 RGB JPEG，再嵌入 ID3v2.3 APIC。手動選擇的共用封面優先於自動封面。

## 重複過濾

預設勾選 **自動略過重複歌曲**：

- 同一首影片即使分別使用 YouTube Music、普通 YouTube 或 youtu.be 網址，也只保留一筆。
- 同一個來源再次貼入會直接略過。
- 歌手、歌名相同且長度相差 3 秒內時，視為相同版本。
- 開始處理後，還會檢查目的資料夾既有 MP3 與來源檔 SHA-256。
- 成功輸出後會更新 `.car-music-dedupe.json`，下次執行仍有效。

需要保留 Live、Remix、鋼琴版或不同演奏版本時，先補完整版本名稱，或取消勾選去重選項。

## 重要限制

- YouTube Music 播放清單有時會被 yt-dlp 轉向普通 YouTube 播放清單；兩邊的版本可能不同。
- 頻道首頁可能同時包含影片、Shorts 或直播，因此程式優先讀取 `/videos`。
- `讀取 YouTube Music` 只代表版本與 metadata 載入，不代表取得下載授權。
- 圖片可自動讀取，不代表遠端音訊自動取得授權；音訊仍必須由使用者逐首確認「有權取得」。
- 目前去重是保守規則，不是聲學指紋。不同編碼但內容相同的歌曲，若網址、標籤和檔案雜湊都不同，仍可能需要人工確認。
