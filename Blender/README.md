# Blender 錯視碎片 PoC

## 使用方式
1. 用 Blender 開啟 `split.blend`；場景已更新為去背版碎片。
2. 在 Scripting 工作區開啟內嵌的 `alpha_background_aware_shards.py`，調整參數後按 Run Script 重新生成。
3. 圖片預設使用 `resource/OIP-removebg-preview.png`。替換圖片後重新執行腳本並儲存場景。
4. 生成後會選取碎片；需要送往 Unity 時，匯出 FBX 並啟用 Selected Objects 與 Apply Modifiers，另將 PNG 複製到 Unity。

## 檔案
- `alpha_background_aware_shards.py`：新版 Alpha 輪廓裁切與不規則後表面延伸程式；場景內嵌相同版本。
- `split.blend`：新版 PoC 場景。
- `resource/`：原始圖片。
- `Backups/`：可選的本機備份資料夾，不納入 Git。

外部程式修改後，請在 Blender 重新載入文字，再執行並儲存，讓內嵌版本同步。
此版仍保留原 PoC 的正交視角驗證方式；尚未加入透視補償、AR 或自動匯出 Unity。

最新版本保留逐頂點厚度變化、背面收縮與隨機偏移，RANDOM_SEED = 10。

已知限制：目前生成的 Shard_002 有一處邊由四個面共用，尚未修整為流形網格。
