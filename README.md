# 🌿 大水大睡大健康 — Health Float

> **大水时代，大睡时代，大眺望时代，大健康时代。**

总是因为忘记喝水而烦恼吗？
总是因为拖延导致晚睡而烦恼吗？
总是因为久坐而担心吗？

**大水大睡大健康 (Health Float)** 帮助你解决这些问题——
提醒你定时喝水💧，定时遵守 **20-20 原则**👀 保护眼睛，定时起来走一走🧘 避免久坐，
晚上提醒你早点去洗澡🛁，然后早点能上床睡觉🌙。

一个**永远置顶**的桌面小舷窗，温柔地提醒你照顾自己。

---

## 📥 怎么用（不懂技术也能用）

### 📦 直接下载成品（推荐）

**[⬇️ 点这里下载 v1.2.0](https://github.com/Nancihahahahahahah/big-water-big-sleep/releases/tag/v1.2.0)**

| 系统 | 下载 | 大小 |
|------|------|------|
| **macOS**（Intel + Apple Silicon 通用） | `Health.Float.dmg` | 36 MB |
| **Windows** | `HealthFloat-Windows.zip` | 11 MB |
| **Linux** | `Health.Float.AppImage` | 24 MB |

**完全不需要装 Python，不需要敲任何命令，不需要看教程。**

### macOS

1. 下载 `Health.Float.dmg`
2. 双击打开，把 `Health Float.app` 拖进「应用程序」文件夹
3. 双击 `Health Float.app` —— 第一次会弹出设置窗口，用**上下箭头**选好洗澡和睡觉时间
4. 想开机自动运行：**系统设置 → 通用 → 登录项 → 点 `+` → 选 Health Float.app**

> 首次打开如果 macOS 提示"无法验证开发者"：在「系统设置 → 隐私与安全性」里点「仍要打开」。

### Windows

1. 下载 `HealthFloat-Windows.zip` 并解压
2. 双击 `Health Float.exe`（绿色小舷窗会出现在屏幕右下角）
3. 想开机自动运行：按 `Win + R`，输入 `shell:startup`，把 `Health Float.exe` 的快捷方式拖进去

> 第一次运行若被 Windows Defender 拦截，点「更多信息 → 仍要运行」。

### Linux

1. 下载 `Health.Float.AppImage`
2. 终端执行 `chmod +x Health.Float.AppImage`（只需一次）
3. 双击运行

> 想看完整说明，去 [`docs/使用手册.md`](docs/使用手册.md)。

---

## 🎛 怎么设置

**点舷窗右下角的 ⚙ 齿轮**（或双击舷窗 / 右键菜单）打开设置面板。

| 想做的事 | 怎么做 |
|---------|--------|
| 改提醒间隔（看远方 / 动一动 / 喝水） | 设置面板里用上下拨轮改分钟数，填 `0` 关闭 |
| 改洗澡 / 睡觉时间 | 设置面板里拨小时和分钟，留空 = 关闭 |
| 开会不想被黑屏 | **右键舷窗 → 会议模式**（或设置面板里的开关） |
| 不想出声但还想被提醒 | **右键舷窗 → 静音模式**（或设置面板里关掉提示音） |
| 临时关掉某类提醒 | 设置面板里填 `0` 或留空 |

设置**保存立即生效**，不用重启。

---

## 🪟 舷窗怎么用

- 平时是一扇固定尺寸的**飞机舷窗**，窗外天空里漂着下一个要来的提醒 icon——喝水快到点就漂 💧，睡觉快到点就漂 🌙，一次只专注一件正事
- 窗下两行小字：倒计时 + 提醒名
- 快到点时（默认提前 2 分钟）整窗开始**轻微呼吸**
- 到点后弹出提醒卡：左边舷窗，右边说明文字
- **⚙ 齿轮 = 打开设置**；**右键 = 快捷菜单**（设置 / 会议模式 / 静音模式 / 退出）
- 拖住可以放到屏幕任意角落

### 🌑 黑屏机制

- 看远方 / 起来活动前 → 全屏黑 **2 秒**
- 洗澡 / 睡觉前 → 全屏黑 **10 秒**
- 黑屏期间**鼠标还在动**（说明你还在工作）→ 继续黑着，直到你真的停下来
- **点一下随时跳过**（安全阀：最多延长 30 次，不会永久锁屏）

### 🎙 会议模式

开会投屏前右键开启 → 提醒照常弹小卡，**绝不全屏黑屏**，绝不抢焦点（你正在打的字不会丢）。

### 🔕 静音模式

提醒照常弹窗，**只是不出声**。适合图书馆、开会、共享空间。

---

## 📁 配置文件在哪

想手动改配置的话（一般不用，用设置面板就行）：

| 平台 | 路径 |
|------|------|
| macOS | `~/Library/Application Support/HealthFloat/config.json` |
| Windows | `%APPDATA%\HealthFloat\config.json` |
| Linux | `~/.config/health-float/config.json` |

```json
{
  "eye_minutes": 20,            // 每 N 分钟看远方，0 = 关闭
  "move_minutes": 60,           // 每 N 分钟起来活动，0 = 关闭
  "water_minutes": 120,         // 每 N 分钟喝水，0 = 关闭
  "shower_time": "21:30",       // 每天洗澡提醒时间
  "sleep_time": "22:30",        // 每天睡觉提醒时间
  "prewarn_seconds": 120,       // 提前多少秒开始呼吸预告，0 = 关闭
  "blackout_seconds": 10,       // 洗澡/睡觉提醒先黑屏 N 秒，0 = 关闭
  "blackout_brief_seconds": 2,  // 眺望/站立提醒先黑屏 N 秒，0 = 关闭
  "meeting_mode": false,        // 会议模式：开启后提醒永不黑屏
  "sound": true,                // 提示音；false = 静音模式
  "opacity": 0.96               // 舷窗透明度 0 ~ 1
}
```

> 配置存在**用户目录**而不是程序目录——所以重装、升级、换电脑都不会丢设置。

---

## 🛠 开发者：从源码运行

```bash
git clone https://github.com/Nancihahahahahahah/big-water-big-sleep.git
cd big-water-big-sleep
python3 health_float.py
```

需要 Python 3.8+ 且带 tkinter。macOS 自带和 Homebrew 的 Python 常常缺 tkinter，
装 [python.org 官方版](https://www.python.org/downloads/) 最省事，或直接双击 `start_mac.command`（会自动帮你找一个能用的）。

### 跑测试

```bash
python3 -m unittest discover -s tests -v
```

CI 会在 macOS / Windows / Linux × Python 3.9/3.11/3.13 上自动跑。

### 打包成安装包

```bash
pip install pyinstaller customtkinter
./build_macos_app.sh          # → dist/Health Float.app（自带 Python，用户零依赖）
```

> `customtkinter` 是**可选**依赖：设置面板用它做现代圆角界面（卡片分组、
> 真按钮、开关）。没装的话程序自动降级到原生 tk 面板，功能一模一样，
> 只是界面朴素些。打包脚本已带 `--collect-all customtkinter`，
> 主题 JSON 和字体文件都会一并打进去。

---

## 🎨 界面设计

设置面板基于 **CustomTkinter**（[13.6k★](https://github.com/TomSchimansky/CustomTkinter)，
tkinter 生态里 star 最高的现代 UI 库）重做：

- **卡片分组**：间隔提醒 / 每日提醒 / 黑屏时长 / 模式开关，四组独立卡片，
  不再是十行平铺
- **真圆角按钮**：保存 / 恢复默认都是 `CTkButton`，带 hover 反馈
- **开关**：`CTkSwitch` 替代系统 Checkbutton
- **拨轮**：圆角输入框 + 圆角 ▲▼ 按钮，比原生 Spinbox 干净

浮窗（Canvas 绘制部分）保持手绘，但：

- 齿轮按钮**不再有白色方框底板**——平时只显示 ⚙ 图标，鼠标移上去
  才淡入一个柔和的圆形底板
- 文字字号放大一档（主文字 10 → 12，副文字 8 → 10），远看也清楚
- 配色统一到一套低饱和莫兰迪灰蓝 token（`C_ACCENT` / `C_SOFT` / `C_LINE`）

---

## ❓ 常见问题

**Q：合盖睡了一夜，醒来会不会被一堆提醒轰炸？**
不会。检测到休眠超过 5 分钟，错过的时间点会静默重排到未来。

**Q：黑屏会不会抢走我正在输入的内容？**
不会。遮罩只做视觉和鼠标层面的强制，不抢键盘焦点。

**Q：Windows 上没有声音？**
Windows 用 `winsound` 发一声提示音；Linux 优先用 `paplay`/`aplay`，都没有就安静跳过——不影响提醒功能。

**Q：想关掉某个提醒？**
设置面板里把它填 `0`（间隔类）或留空（时间类）。

---

## License

[MIT](LICENSE)
