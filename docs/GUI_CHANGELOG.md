# GUI 變更摘要

## 0.3.0

- 新增專用的 **讀取 YouTube Music** 按鈕。
- 支援 metadata-only 的歌曲、播放清單、專輯播放清單與藝人頻道網址。
- 自動移除 `si` 等常見追蹤參數。
- 對 YouTube Music 藝人與播放清單使用有順序的 metadata fallback。
- 可用時預填歌手、歌名、專輯、長度與頻道。
- Metadata 讀取與遠端來源授權確認保持分離。

## 0.2.0

- 新增 `car-music-gui` 桌面啟動指令。
- 新增 PySide6 操作介面。
- 新增網址 metadata 載入、本機音訊匯入與曲目表格。
- 新增目的地選擇、新增資料夾、共用封面與 Corolla Cross 保守 Profile。
- 新增背景批次處理、進度、取消與每首錯誤隔離。
- 新增 JPEG 封面轉換及 ID3v2.3 APIC 寫入。
- 新增 GUI helper 與封面測試。
