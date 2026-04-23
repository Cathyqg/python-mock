# Python Mock

## 随机鼠标和按键测试脚本

脚本位置：

```powershell
random_input_test.py
```

这个脚本用于手动 UI smoke test：在一段时间内随机移动鼠标，并随机模拟按 `Alt` 和 `CapsLock`。默认是 dry-run 模式，只打印将要执行的动作，不会真的移动鼠标或按键。

### 先 dry-run 验证

```powershell
py -3 -B random_input_test.py
```

这会输出类似：

```text
[dry-run] move mouse to (...)
[dry-run] press Alt
[dry-run] press CapsLock
```

### 真正执行

真正发送鼠标和键盘事件需要加 `--live`：

```powershell
py -3 -B random_input_test.py --live --duration 30 --max-actions 100
```

含义：

- `--live`：实际移动鼠标和按键。
- `--duration 30`：最多运行 30 秒。
- `--max-actions 100`：最多执行 100 个随机动作。

### 跑两个小时

两小时是 `7200` 秒。建议设置较长的动作间隔，避免过于频繁地干扰当前窗口：

```powershell
py -3 -B random_input_test.py --live --duration 7200 --max-actions 1000 --min-delay 10 --max-delay 30
```

效果：脚本会在 2 小时内，每隔 10 到 30 秒随机执行一次动作，直到达到 7200 秒、达到 1000 次动作，或者被手动停止。

### 只随机移动鼠标

如果只想保持鼠标活动，不想按 `Alt` 或 `CapsLock`：

```powershell
py -3 -B random_input_test.py --live --duration 7200 --max-actions 1000 --min-delay 10 --max-delay 30 --mouse-prob 1 --alt-prob 0 --caps-prob 0
```

### 鼠标为主，偶尔按键

```powershell
py -3 -B random_input_test.py --live --duration 7200 --max-actions 1000 --min-delay 10 --max-delay 30 --mouse-prob 0.85 --alt-prob 0.10 --caps-prob 0.05
```

含义：

- `--mouse-prob 0.85`：约 85% 的动作是移动鼠标。
- `--alt-prob 0.10`：约 10% 的动作是按 `Alt`。
- `--caps-prob 0.05`：约 5% 的动作是按 `CapsLock`。

### 常用参数

```powershell
py -3 -B random_input_test.py --help
```

常用参数说明：

- `--duration`：最长运行秒数。
- `--max-actions`：最多执行动作次数。
- `--min-delay` / `--max-delay`：两次动作之间的随机等待时间。
- `--seed`：固定随机种子，方便复现同一组随机动作。
- `--margin`：鼠标移动时避开屏幕边缘的像素距离。
- `--corner-abort-margin`：鼠标靠近屏幕角落时自动停止的距离，默认 `10`。
- `--no-restore-caps-lock`：退出时不恢复原始 `CapsLock` 状态。

### 停止方式

- 在终端按 `Ctrl+C`。
- 把鼠标移动到屏幕任意角落附近，脚本会自动停止。

### 注意事项

- `Alt` 可能会激活当前窗口菜单或触发应用快捷键。
- `CapsLock` 会被随机切换，但脚本默认会在退出时恢复原始状态。
- 建议先用 dry-run 或短时间 live 测试确认效果：

```powershell
py -3 -B random_input_test.py --live --duration 30 --max-actions 10
```

