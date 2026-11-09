# 🌿 大水大睡大健康 — Health Float

> **大水时代，大睡时代，大眺望时代，大健康时代。**

总是因为忘记喝水而烦恼吗？
总是因为拖延导致晚睡而烦恼吗？
总是因为久坐而担心吗？

**大水大睡大健康 (Health Float)** 帮助你解决这些问题——
提醒你定时喝水💧，定时遵守 **20-20 原则**👀 保护眼睛，定时起来走一走🧘 避免久坐，
晚上提醒你早点去洗澡🛁，然后早点能上床睡觉🌙。

一个**永远置顶**的桌面小卡片，温柔地提醒你照顾自己：

| 提醒 | 默认频率 |
|------|---------|
| 👀 看远方 20 秒（护眼） | 每 20 分钟 |
| 🧘 站起来动一动 | 每 1 小时 |
| 💧 喝杯水 | 每 2 小时 |
| 🛁 去洗澡 | 每天 21:30 |
| 🌙 早点睡觉 | 每天 22:30 |

纯 Python 标准库实现（tkinter），**零依赖**，clone 下来就能跑。
支持 macOS / Windows / Linux。

## 快速开始

```bash
git clone https://github.com/Nancihahahahahahah/big-water-big-sleep.git
cd health-float
python3 health_float.py
```

> 前提：电脑上装有 Python 3.8+（tkinter 一般自带）。

### 各平台启动方式

- **macOS**：双击 `start_mac.command`，或终端运行上面的命令
- **Windows**：双击 `start_windows.bat`（用 `pythonw` 启动，不弹黑框）
- **Linux**：运行 `./start_linux.sh`

## 自定义提醒频率

首次运行会自动生成 `config.json`，直接用任意编辑器改即可：

```json
{
  "eye_minutes": 20,        // 每 N 分钟看远方，0 = 关闭
  "move_minutes": 60,       // 每 N 分钟起来活动，0 = 关闭
  "water_minutes": 120,     // 每 N 分钟喝水，0 = 关闭
  "shower_time": "21:30",   // 每天洗澡提醒时间，"" = 关闭
  "sleep_time": "22:30",    // 每天睡觉提醒时间，"" = 关闭
  "sound": true,            // 提醒时播放提示音（仅 macOS）
  "opacity": 0.88           // 待机时卡片透明度 0 ~ 1
}
```

改完重启脚本生效。

## 小卡片怎么用

- 拖住卡片可以放到屏幕任意角落
- 点右上角 `—` 折叠成一个小 🌿，再点展开
- 提醒弹出时会"叮"一声并高亮；看远方提醒自带 20 秒倒计时，其余会自动消失，也可点「知道了 ✓」立即关掉

## 开机自启（可选）

- **macOS**：系统设置 → 通用 → 登录项 → 添加 `start_mac.command`
- **Windows**：`Win + R` 输入 `shell:startup`，把 `start_windows.bat` 的快捷方式放进去
- **Linux**：把 `start_linux.sh` 加入桌面环境的自启程序列表

## 常见问题

**macOS 报错 `macOS (1507) or later required`？**
这是 macOS 系统自带 Python 的 tkinter 兼容 bug。去 [python.org](https://www.python.org/downloads/) 装官方 Python 3，用它运行即可。

**Windows 上没有声音？**
提示音用的是 macOS 系统音效，Windows/Linux 下会自动静默，不影响提醒功能。

## License

[MIT](LICENSE)
