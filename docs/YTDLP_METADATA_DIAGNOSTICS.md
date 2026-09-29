# yt-dlp pipeline authentication 排查與修正

檢查日期：2026-09-29。專案：`C:\Projects\car-music-manager`。

本次補齊整個 pipeline：四個 public entry points 都透過 `ytdlp_metadata.py` 的同一個 authentication loop。`list_youtube()`、`list_ytmusic()`、`search_youtube()` 透過 `extract_metadata()` 呼叫 `extract_with_authentication(download=False)`；`download_authorized()` 直接呼叫 `extract_with_authentication(download=True)`，並在成功的 downloader context 內取得 `prepare_filename()`。下方現場診斷保留初次 metadata 排查的證據與限制。

## A. 問題根因與證據

1. GUI 使用專案 `.venv` 的 Python package，不是另一個全域 yt-dlp。實際版本為 `2026.08.19`；`car_music_manager` 從本專案 `src` 載入。
2. 修改前四處 `YoutubeDL(options)` 都沒有 `cookiesfrombrowser` 或 `cookiefile`。Python API 不會因為曾經在 PowerShell 執行 `--cookies-from-browser chrome` 就記住該設定，也不會自動套用 yt-dlp CLI config。
3. 對使用者指定影片執行匿名 CLI metadata 測試，確實得到 `Sign in to confirm you're not a bot`。這代表 YouTube 對該次請求要求驗證，不能只憑這個訊息斷定是 IP 封鎖、帳號問題或影片本身不可用。更新程式版本不會自動解決驗證要求。
4. `Could not copy Chrome cookie database` 是另一層問題：yt-dlp 還在複製本機 cookie SQLite 資料庫，尚未完成 cookie 載入，更沒有用它成功向 YouTube 驗證。
5. 檢查時有 Chrome 背景程序；只嘗試開啟檔案 handle，沒有讀取內容，確認 `Default`、`Profile 1`、`Profile 3` 的 `Network/Cookies` 回報 Windows 分享違規碼 32。此版 yt-dlp 未指定 profile 時選最近修改的 Cookies 檔，檢查時是 `Profile 3`。所以資料庫鎖定是目前 CLI 複製失敗的直接證據，而不是僅從錯誤字串猜測。
6. 關閉所有 Chrome 視窗仍可能有背景程序；即使複製成功，DPAPI／Chrome App-Bound 加密也可能造成解密失敗。這兩個階段必須分開看，不能保證退出 Chrome 就能讀到可用 cookies。官方追蹤：[Windows 資料庫鎖定 #7271](https://github.com/yt-dlp/yt-dlp/issues/7271)、[Windows cookie 解密 #10927](https://github.com/yt-dlp/yt-dlp/issues/10927)。
7. YouTube Music 原本 `ignoreerrors=True`，可能把 extraction error 變成 `None` 或含 `None` 的 playlist。原本最後只顯示沒有 metadata／沒有曲目，無法據此觸發 authentication fallback。
8. Qt worker 原本將 exception 直接插入字串，再交給 `QMessageBox.warning`。yt-dlp 的 `YoutubeDL.report_error()` 會依終端能力替 `ERROR:` 加色碼；色碼也可能包含在 `DownloadError` 中。`quiet=True` 不等於取消顏色，Qt 不會解讀終端 ANSI。

現場驗證的限制：匿名 CLI 曾重現 bot error，但稍後呼叫本專案的 `list_youtube()` 和 `list_ytmusic()`，同一影片均匿名成功。CLI `--skip-download` 與 GUI 的 flat extraction 設定也不同，不能將兩者結果當成完全相同的測試。驗證要求會受請求路徑及當下 YouTube 狀態影響；此修正提供重試與診斷，不代表能保證解除驗證。

## B. 實際呼叫流程

入口：`car-music-gui.exe` → `pyproject.toml` 的 `car_music_manager.gui_ytmusic:main` → `QApplication` → `YTMusicMainWindow(MainWindow)`。

一般網址：

```text
「讀取網址」clicked
→ MainWindow.load_urls()
→ MetadataLoader.start() / run()
→ youtube.list_youtube(url)
→ ytdlp_metadata.extract_metadata(url, options)  [本次新增]
→ yt_dlp.YoutubeDL(options).extract_info(url, download=False)
→ loaded signal
→ YTMusicMainWindow._metadata_loaded()
→ 加入表格／QMessageBox.warning
```

YouTube Music：

```text
「讀取 YouTube Music」clicked
→ YTMusicMainWindow.load_ytmusic_urls()
→ YTMusicMetadataLoader.start() / run()
→ ytmusic.list_ytmusic(url)
→ ytmusic_candidate_urls(url)
→ ytdlp_metadata.extract_metadata(candidate, options)  [本次新增]
→ yt_dlp.YoutubeDL(options).extract_info(candidate, download=False)
→ loaded signal
→ YTMusicMainWindow._ytmusic_metadata_loaded()
→ 加入表格／QMessageBox.warning
```

原本 URL fallback 保留：歌曲、playlist 優先 Music 網域再試普通 YouTube；藝人頁依序試普通 YouTube `/videos`、普通藝人首頁、Music URL。Authentication/cookie failure 現在直接回 GUI，不再重複對同一問題嘗試各種 URL。

## C. 涉及的檔案、行數與 options

行數以修改後版本為準。

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `pyproject.toml` | 18、26 | yt-dlp dependency、GUI entry point |
| `src/car_music_manager/__main_gui__.py` | 3 | module GUI entry point |
| `src/car_music_manager/gui.py` | 98、107、229、359 | 一般網址 loader、button、load_urls |
| `src/car_music_manager/gui_ytmusic.py` | 41、50、265、304 | Music loader、button、load_ytmusic_urls |
| `src/car_music_manager/gui_ytmusic.py` | 327、353、501 | 兩種結果 handler、實際 GUI main |
| `src/car_music_manager/youtube.py` | 38、43、85、92 | metadata listing、authorized download 與 options |
| `src/car_music_manager/ytmusic.py` | 97、186、191、201 | URL candidates、listing 與 options、helper 呼叫 |
| `src/car_music_manager/youtube_candidates.py` | 98、104、112 | metadata search 的第三個直接 API 入口 |
| `src/car_music_manager/ytdlp_metadata.py` | 15、19、53、94、120 | 新增 authentication exception、ANSI 清理、設定、錯誤轉譯、fallback |
| `.gitignore` | 13–16 | `.env`、local config、`cookies*.txt`、archive ignore |
| `tests/test_ytmusic.py` | 1 | 既有 URL normalization、classification、entry conversion tests |
| `tests/test_gui.py` | 1 | 既有 GUI helpers／artwork tests |
| `tests/test_ytdlp_metadata.py` | 1 | 本次新增 extraction／fallback／GUI error tests |

修改前 options：

| 入口 | options |
| --- | --- |
| `list_youtube` | `quiet=True`, `extract_flat=True`, `skip_download=True`, `noplaylist=False` |
| `list_ytmusic` | `quiet=True`, `no_warnings=True`, `skip_download=True`, `extract_flat='in_playlist'`, `ignoreerrors=True`, `noplaylist=False`, `playlistend=max_entries`（預設 500） |
| `search_youtube` | `quiet=True`, `skip_download=True`, `extract_flat='in_playlist'`, `noplaylist=True`, `socket_timeout=15` |
| `download_authorized` | `format='bestaudio/best'`, `outtmpl=<temporary destination>`, `noplaylist=True`, `quiet=True`, `restrictfilenames=False` |

所有四處都直接使用 Python API，不經 yt-dlp subprocess。`tools.py`／相關 tests 的 subprocess 是外部工具處理，不是這條 yt-dlp 呼叫路徑。呼叫端另包括 `cli.py:123`、`batch.py:100`、`gui.py:159`、`gui_ytmusic.py:133`、`scripts/build_catalog.py:85`、`scripts/search_youtube_candidates.py:43`。README、GUI docs、manual-review scripts 還有 yt-dlp／YouTube 的文字引用，並非額外 extractor 入口。

## D. 建議修正方案

| 方案 | Windows 評估 | 本專案建議 |
| --- | --- | --- |
| 每次直接使用 Chrome | 活躍 Chrome 的資料庫鎖定、解密、選錯 profile 都可能失敗 | 支援，但不硬編碼成必定成功的預設 |
| 使用 Firefox | 避開 Chrome 專屬鎖定／App-Bound 路徑；仍需正確 profile、有效 YouTube session | 若已安裝且願意登入，優先作為 browser fallback；未實測登入成功 |
| 外部 `cookies.txt` | 避開執行時複製 Chrome DB；需 Netscape 格式、手動匯出與更新 | Chrome 不可讀或無 Firefox 時的備援；放在 repo 外 |
| 匿名後才使用選定 cookies | 匿名成功不碰瀏覽器，auth 失敗才重試，避免一般網路錯誤觸發 cookie 載入 | 最適合；搭配可設定 Firefox／Chrome／cookie file |

不要同時設定 browser 與 cookie file，以免混合 session。Browser API option 是 tuple，例如 `('chrome', 'Profile 3', None, None)`，不是 CLI 字串 `chrome:Profile 3`。

YouTube cookies 會輪替；文字檔不代表永久有效。匯出時依官方 [Exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) 操作，僅匯出需要的網站 cookies，避免把所有網站 cookies 一起匯出。檔案需 Mozilla/Netscape 格式，詳見 [FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)。

## E. 最小修改與理由

1. 新增 `ytdlp_metadata.py`：四個入口共用 anonymous → auth detection → one configured retry；cookie source parsing、錯誤診斷及 retry loop 都只實作一次。透過 in-memory logger 找回被 `ignoreerrors` 吞掉的錯誤；保留已有可用項目的 partial playlist 行為。
2. 修改 `youtube.py` 的 `list_youtube()`：只把 metadata API 呼叫交給 helper，原有 options、模型與去重不變。
3. 修改 `ytmusic.py` 的 extraction 呼叫：共用 helper；authentication/cookie failure 不再重跑候選 URL。其他錯誤仍保留原本 URL fallback，顯示前清除 ANSI。
4. 修改 `youtube_candidates.py` 的 `search_youtube()`：查詢字串、options、排序與結果上限保留，extraction 改走共用 helper。
5. 修改 `download_authorized()`：以原本的下載 options 執行同一套 fallback；保留 format、filename template、單一影片與副檔名 fallback。Metadata 匿名成功後，download 若需要 authentication，仍能獨立使用同一份設定重試。
6. helper 設 `no_color=True`，並清理 exception 字串；兩個 GUI metadata loader 與兩個 processing worker 在送出錯誤 signal 前也清除 ANSI。
7. 移除 `list_ytmusic()` 的重複 metadata 型別檢查，該檢查已由共用 helper 保證。保留 exception chain 診斷與 partial playlist 判斷，因為分別支援包裝 cookie error 與 `ignoreerrors=True`。
8. 新增測試：驗證四個 public entry points 的匿名成功、Chrome／Firefox／profile／cookie file fallback、重試上限、無設定、無關錯誤、ANSI、pipeline 下載、options 與檔名行為。

不增加 GUI 設定頁或 dependency；下載及 search 現在共用 authentication 設定。每次操作先匿名，匿名成功不解析或載入 cookie 來源，只有 authentication failure 才讀取環境變數並重試一次。沒有快取 browser session、合併 cookie 來源或加入新的 credential 管理層。

`reports/yt-dlp-metadata-fallback.patch` 是前次 metadata 修正的歷史快照，不包含本次 pipeline 補齊；目前工作區才是本次修改結果。此報告不包含 cookie 值、token 或登入資訊；沒有建立、匯出、commit 或 stage 真實 cookie 檔。既有 `.gitignore` 保護 `cookies*.txt`，也已確認 Git 未追蹤這類檔案。

## F. 測試方法與结果

初次 metadata 修正前：69 tests passed；初次修正後：95 tests passed。本次 pipeline 補齊後：132 tests passed（本次再增加 37 個案例）；全 repo Ruff lint 通過。

測試涵蓋匿名成功不碰 cookies、Chrome／Firefox tuple 與 profile、bot failure 後一次重試、未設定 provider 的指引、429／timeout／不可用影片不觸發 cookie fallback、Chrome lock、DPAPI、cookie 載入失敗、包裝 exception chain、重試仍需驗證、Music swallowed error、全部 playlist entries 失敗、partial playlist 保留、Music URL fallback、去重、cookie path／provider 設定錯誤、ANSI 清理與 Qt worker signal。

測試均使用 fake `YoutubeDL`，不讀取真實瀏覽器 session。另以真實匿名 API 測試一般 YouTube 及 Music metadata，各得到 1 個 entry。尚未完成真實 cookie 驗證成功的測試；沒有為了測試而終止 Chrome 或變更加密設定。未實際點擊 GUI 視窗，Qt worker 訊息路徑有 unit test。

手動 GUI：重新啟動後分別按兩個讀取按鈕，確認成功時加入表格，bot error 有設定指引，Chrome lock 有退出／改來源指引，視窗中沒有 ANSI 色碼；再確認 artist／playlist 仍保持原有 URL fallback 與去重。

## G. PowerShell 驗證指令

```powershell
Set-Location 'C:\Projects\car-music-manager'
$videoUrl = 'https://youtube.com/watch?v=Z8U-QqtJXMA'

# 確認實際 Python、yt-dlp 與專案載入路徑
.\.venv\Scripts\python.exe -c "import sys,yt_dlp,yt_dlp.version,car_music_manager; print(sys.executable); print(yt_dlp.version.__version__); print(yt_dlp.__file__); print(car_music_manager.__file__)"

# 匿名 CLI：排除全域／使用者 CLI config，僅讀 metadata
.\.venv\Scripts\python.exe -m yt_dlp --ignore-config --no-colors `
    --socket-timeout 10 --retries 0 --extractor-retries 0 `
    --skip-download --print '%(title)s' $videoUrl

# Chrome 狀態；先自行儲存工作並完整退出 Chrome，再重測
Get-Process chrome -ErrorAction SilentlyContinue | Select-Object ProcessName,Id
# 請把 Profile 3 改成實際登入 YouTube 的 profile；不是顯示名稱
.\.venv\Scripts\python.exe -m yt_dlp --ignore-config --no-colors `
    --cookies-from-browser 'chrome:Profile 3' `
    --skip-download --print '%(title)s' $videoUrl

# 若已安裝 Firefox 並登入 YouTube
.\.venv\Scripts\python.exe -m yt_dlp --ignore-config --no-colors `
    --cookies-from-browser firefox --skip-download --print '%(title)s' $videoUrl

# GUI 選用 Chrome fallback，只有 auth error 才讀取
Remove-Item Env:CAR_MUSIC_YTDLP_COOKIE_FILE -ErrorAction SilentlyContinue
$env:CAR_MUSIC_YTDLP_BROWSER = 'chrome'
$env:CAR_MUSIC_YTDLP_PROFILE = 'Profile 3'
.\.venv\Scripts\car-music-gui.exe

# 或選用 Firefox fallback；先結束舊 GUI，再執行
Remove-Item Env:CAR_MUSIC_YTDLP_COOKIE_FILE -ErrorAction SilentlyContinue
Remove-Item Env:CAR_MUSIC_YTDLP_PROFILE -ErrorAction SilentlyContinue
$env:CAR_MUSIC_YTDLP_BROWSER = 'firefox'
.\.venv\Scripts\car-music-gui.exe

# 或使用已自行匯出、存放於專案外的 Netscape cookies.txt
Remove-Item Env:CAR_MUSIC_YTDLP_BROWSER -ErrorAction SilentlyContinue
Remove-Item Env:CAR_MUSIC_YTDLP_PROFILE -ErrorAction SilentlyContinue
$env:CAR_MUSIC_YTDLP_COOKIE_FILE = Join-Path $env:LOCALAPPDATA 'CarMusicManager\cookies.txt'
Test-Path -LiteralPath $env:CAR_MUSIC_YTDLP_COOKIE_FILE
.\.venv\Scripts\python.exe -m yt_dlp --ignore-config --no-colors `
    --cookies $env:CAR_MUSIC_YTDLP_COOKIE_FILE --skip-download --print '%(title)s' $videoUrl
.\.venv\Scripts\car-music-gui.exe

# 直接測專案的兩條 metadata 路徑，使用目前 shell 的 fallback 設定
.\.venv\Scripts\python.exe -X utf8 -c "from car_music_manager.youtube import list_youtube; print(list_youtube('https://youtube.com/watch?v=Z8U-QqtJXMA'))"
.\.venv\Scripts\python.exe -X utf8 -c "from car_music_manager.ytmusic import list_ytmusic; print(list_ytmusic('https://music.youtube.com/watch?v=Z8U-QqtJXMA'))"

# 完整 tests、相關 lint 與 patch 檢查
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git diff --check

# 完成後清除本 shell 設定；不影響已啟動的 GUI
Remove-Item Env:CAR_MUSIC_YTDLP_BROWSER,Env:CAR_MUSIC_YTDLP_PROFILE,Env:CAR_MUSIC_YTDLP_COOKIE_FILE -ErrorAction SilentlyContinue
```

環境變數只影響此 PowerShell 啟動的子程序；已開啟的 GUI 必須退出再重啟。`CAR_MUSIC_*` 由本專案 helper 讀取，yt-dlp CLI 不會自動讀這些自訂設定，CLI 必須另外傳 `--cookies-from-browser` 或 `--cookies`。以上方案擇一執行，不需要全部依序設定。
