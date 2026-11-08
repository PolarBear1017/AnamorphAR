# 圓形錯視碎片 PoC

## 查看目前版本


直接開啟 **`circular_earth_fragments.blend`**，數字鍵盤 **0** 進入相機視角，按 **Space** 播放。第 **1 / 160** 格拼回地球；第 **45 / 90** 格可看到偏離視角的碎片。播放時不要移動 `Illusion_Rotate_This`，避免改變解答位置。也可先停止播放，在相機視角外以滑鼠中鍵繞行觀察。

- `circular_fragments.py`：450 個隨機 Voronoi 多邊形，各片有獨立厚度與收縮背面。前後散布範圍 ±6；依指定透視相機的射線補償位置與大小。
- 圖片材質、圖片本身與腳本已內嵌到 `.blend`。原始 `split.blend` 保留。
- `previews/earth_aligned.png` / `previews/earth_scattered.png`：實際 Blender 相機渲染。
- 要調整片數：在 Scripting 開啟內嵌 `circular_fragments.py`，修改 `SHARD_COUNT` 再執行。腳本需讀取本資料夾的 `resource/earth_apollo17.png`。會重建自己的集合並隱藏其他場景物件。
- `GAP` 預設 0.008，保留細微切縫；若需要接近無縫，設為 0。特定視角附近會有逐漸對齊的容許範圍，並非只有一個離散角度能看見。
- 這份是 Blender 模型與視角示範，尚未接入 Unity 手機陀螺儀、觸控旋轉或完成判定。手機實作需讓相機繞模型中心公轉，或旋轉模型根節點；單純在固定相機位置改變朝向不會產生所需視差。指定相機在 (0,0,18)，朝 -Z，45mm / 36mm sensor（正方形畫面水平視角約 43.6°）。

### 圖片來源

NASA / Apollo 17, “The Earth seen from Apollo 17 with transparent background”。Commons 標記為美國公有領域；透明背景衍生版的製作者資訊見來源頁。

來源：https://commons.wikimedia.org/wiki/File:The_Earth_seen_from_Apollo_17_with_transparent_background.png

下載：https://upload.wikimedia.org/wikipedia/commons/4/43/The_Earth_seen_from_Apollo_17_with_transparent_background.png

已檢查 450 片幾何的圓形邊界與透視投影回復誤差（最大約 8.9e-16）。新版亦已在 Blender 5.2.3 成功建立、儲存並渲染。

## 早期球殼實驗


在 Blender 開啟新場景，先儲存在本資料夾，再於 Scripting 開啟並執行 `spherical_illusion.py`。執行後另存為 `sphere_split.blend`。請用數字鍵盤 0 查看指定的正交相機；旋轉視角可看到球面碎片的深度分散。

- 完整球面依正面 XY 投影的 Voronoi 區域分為 9 片，沿 Z 軸分散；正交相機下保留圖像對齊。
- 圖片以中央正方形裁切投影到球面，外框為圓形；透明部分填入深色背景。
- `RADIUS` 控制球半徑，`SHARD_COUNT` 控制片數，`DEPTH_SCATTER` 控制深度分散（設為 0 可查看組合球），`SHELL_THICKNESS` 控制球殼厚度。
- 使用自發光材質保持圖片顏色，球面立體感可由側視幾何觀察。這是球殼碎片，不是每片各自變成小圓球。
- 再執行只會取代 `SphericalIllusion` 集合；場景中其他物件會隱藏。原始 `split.blend` 不會被覆寫。
- 已通過 Python 語法檢查；早期嘗試中 Blender 在背景啟動時崩潰，因此尚未完成 Blender 執行與渲染驗證，也未產生新的 `.blend` 或預覽圖。
