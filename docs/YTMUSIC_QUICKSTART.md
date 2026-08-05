# YouTube Music 專用讀取功能

此功能只讀取 `music.youtube.com` 的曲目資料，不會因為按下讀取按鈕就下載音訊。

## 啟動

```powershell
Set-Location "C:\Projects\car-music-manager"
git switch feat/gui-mvp
git pull
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

支援的常見網址形式：

```text
https://music.youtube.com/watch?v=...
https://music.youtube.com/playlist?list=...
https://music.youtube.com/@artist
https://music.youtube.com/channel/...
```

對藝人網址，程式會優先嘗試相對穩定的普通 YouTube `/videos` metadata 頁，再退回藝人首頁及原始 YouTube Music URL。播放清單或專輯則優先保留 YouTube Music URL，失敗時再嘗試普通 YouTube 對應網址。

## Metadata

可讀取時，程式會優先使用 yt-dlp 回傳的：

- track / title
- artist / creator
- album
- duration
- uploader / channel
- thumbnail URL

目前 GUI 會直接顯示歌手、歌名、專輯、長度與頻道。縮圖網址已保留在 metadata 模型中，後續可再加入逐曲封面預覽及經確認後嵌入。

## 重要限制

- YouTube Music 播放清單有時會被 yt-dlp 轉向普通 YouTube 播放清單；兩邊的版本可能不同。
- 頻道首頁可能同時包含影片、Shorts 或直播，因此程式優先讀取 `/videos`。
- `讀取 YouTube Music` 只代表版本與 metadata 載入，不代表取得下載授權。
- 遠端來源仍必須由使用者明確勾選 **有權取得**，才會交給既有下載與後製流程。
