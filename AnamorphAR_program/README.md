# AnamorphAR 遊戲主專案

## 開啟專案

1. 安裝 Unity Hub 與 Unity Editor **6000.6.7f1**。
2. 下載（clone）整個 AnamorphAR 儲存庫。
3. 在 Unity Hub 使用 Add，選擇此 `AnamorphAR_program` 資料夾。
4. 等待套件安裝與素材匯入完成，再開始編輯。

本專案使用 Universal 3D（URP）。AI Assistant 的使用權限依各組員帳號而定。

## 共同開發

- 每次開始前先取得遠端最新進度（pull），並建立自己的功能分支。
- 一個分支處理一項功能，完成後提交（commit）、上傳（push），再建立 Pull Request 供組員檢查與合併。
- 避免同時修改同一個 Scene；先分配場景負責人，獨立物件盡量做成 Prefab。
- 在 Unity 編輯器中移動或重新命名素材，並將 `.meta` 檔和素材一起提交。
- 共同維護 `Assets`、`Packages`、`ProjectSettings`；`Library`、`Temp`、`Logs`、`UserSettings` 由各自電腦產生，不上傳。
- 更新 Unity 或套件版本前先和組員協調。

## 首次交接確認

- 用另一個資料夾或組員電腦重新 clone，確認能用指定版本開啟。
- 確認 Console 沒有紅色錯誤，且範例場景能進入 Play 模式。
