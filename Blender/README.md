# Blender 錯視模型驗證

依實驗分類；Unity 遊戲專案仍位於 `../AnamorphAR_program/`。

| 資料夾 | 內容 | 開啟檔案 |
| --- | --- | --- |
| `01_Alpha_Shards_PoC/` | 原始去背圖片、不規則延伸碎片 | `split.blend` |
| `02_Circular_Anamorphosis_PoC/` | 圓形地球、450 片透視錯視與早期球殼實驗 | `circular_earth_fragments.blend` |
| `Backups/` | 本機備份與舊快取，不納入 Git | — |

每個 PoC 都有自己的 README、生成腳本與 `resource/` 圖片，圓形版本的渲染圖位於 `previews/`。

查看最新圓形錯視：開啟 `02_Circular_Anamorphosis_PoC/circular_earth_fragments.blend`，數字鍵盤 0 進入相機視角，空白鍵播放。第 1 格拼回地球，第 45 格觀看散開效果。

請先將場景儲存在對應 PoC 資料夾，再執行該資料夾內的腳本，以正確讀取相對的圖片路徑。
