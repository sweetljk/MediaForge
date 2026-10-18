# MediaForge 0.1.0 验证报告

验证日期：2026-10-18。工作区：`D:\MediaForge`。

## 完整便携版更新

在初次交付基础上增加 EXE 相对路径引擎检测及完整便携构建。更新后的全量测试为 **126 passed in 124.48s**，没有失败或跳过，原始记录为 `artifacts/portable-test-results.xml`。新增 7 项测试覆盖标准便携布局、原 dist 布局、中文及空格目录、工作目录变化与手动配置优先级。

`release/MediaForge/MediaForge.exe` 在空引擎路径配置、清除引擎环境变量、PATH 仅含 Windows System32、工作目录不同于 EXE 目录的条件下，已通过窗口启动与 6 条真实转换。记录为 `artifacts/portable-check/report.json`，截图为同目录的 `packaged-ui.png`。此轮没有使用 VBS 启动器。

完整便携 ZIP：`release/MediaForge-0.1.0-windows-x64-portable.zip`，737,152,698 字节。附带 SHA256 文件。该验证仍在本机 Windows 11 x64 上进行，不等同于另一台全新电脑的验收。下面保留初次交付的验证记录与原 EXE 哈希；便携版属于单独构建。

压缩包 CRC 完整性检查已通过，并实际解压到 `artifacts/便携包 解压验收`。解压后的 EXE 在相同隔离条件下再次通过窗口启动及 6 条真实转换。记录：`artifacts/portable-extracted-check/report.json`。压缩包中不含 VBS 或 MSI 文件。

## 验证结论

- 全量 pytest：**119 passed in 94.94s**，没有失败或跳过。原始结果：`artifacts/test-results.xml`。
- Windows 打包程序：窗口启动通过，**6 条真实转换流程全部通过**。结果：`artifacts/package-check/report.json`。
- 源码窗口的深色、浅色主题均已运行检查；打包窗口截图：`artifacts/package-check/packaged-ui.png`。
- 样例文件由测试自动生成，未使用用户个人文件。所有转换产物均来自真实引擎执行。

## 环境

本轮验证在 Windows 11 家庭版中文版（10.0.26200）上进行。Python 3.14.5、PySide6 6.12.0、Pillow 12.3.0、PyMuPDF 1.28.2、pypdf 6.21.0、pytest 9.1.1、PyInstaller 6.22.3。完整锁定版本见 `requirements-tested.txt`。

媒体引擎为 FFmpeg / FFprobe 9.0.2；文档引擎为 LibreOffice 26.2.6.3。工具位于项目 `.tools`，未安装到系统目录。来源、校验值与许可证记录见 `TOOLS_PROVENANCE.md` 和 `THIRD_PARTY_NOTICES.md`。ImageMagick 未安装，不影响当前 Pillow 图片转换。

## 实际转换范围

| 类别 | 已验证内容 |
|---|---|
| 视频 | MP4、MKV、MOV、AVI、WebM、M4V 输出；使用 FFmpeg 完整解码输出检查有效性 |
| 音频 | MP3、WAV、FLAC、AAC、M4A、OGG、Opus、AIFF 输出及解码；提取、裁剪、静音；短音轨与较长视频的时长验证 |
| 图片 | PNG、JPEG、WebP、BMP、TIFF、GIF；透明度、多帧和 EXIF 相关处理；中文、空格及超过 260 字符的路径 |
| 文档 | 无 LibreOffice 的 TXT→HTML；TXT→PDF；TXT→DOCX→PDF；CSV→XLSX→PDF；自动生成的 ODP→PPTX→PDF。Office PDF 结果检查页数与文本 |
| PDF | 合并、拆分、提取、页面转图片、图片转 PDF；加密输入拒绝与取消处理 |

打包程序单独验证 PNG→JPEG、TXT→HTML、PDF→PNG、视频→MKV、视频→MP3、TXT→PDF；检查任务成功及非空产物。各类实际样例保留在 `artifacts/package-check`。

## 关键逻辑与回归覆盖

文件识别、引擎匹配、命令参数、编码与容器兼容性、实际进度解析、输出重名和源文件保护、任务状态、取消和超时、缺失工具提示、损坏文件、失败清理、历史记录及 UI 后台事件均有自动化检查。

本轮修复并验证了以下问题：

- Windows 子进程启动器退出后，仍通过 Job Object 终止其工作进程，避免取消遗留进程。
- 原生图片、PDF 和文档工作进程以事件文件传递进度，支持没有标准输出的窗口版 EXE。
- 多输出发布失败可回滚；复制回退路径不会误删其他进程刚创建的目标文件。
- SQLite 连接及时关闭，避免遗留文件锁。
- 图片预检和信息读取保持后台工作对象及信号接收对象有效，避免队列操作停滞。
- Windows LibreOffice 优先使用 `soffice.com`，正确等待转换结束。
- 打包排除开发环境 PATH 中误收集的第三方 ICU DLL，使用系统 ICU，解决 Qt 窗口启动失败。

## 重现

在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/test-results.xml
.\build.ps1
.\.venv\Scripts\python.exe scripts/verify_package.py
```

双击 `Start MediaForge.vbs` 启动已构建程序；该入口为当前进程指定项目内的 FFmpeg、FFprobe 和 LibreOffice。此入口已实际启动，确认窗口标题为“MediaForge · 本地格式转换”。分发时须保留整个 `dist\MediaForge` 文件夹，转换工具另行配置。

本次 `MediaForge.exe` 的 SHA256：`0AEE86046F7A351EC6D77EBC5195D59EF1F975FB4EEF54EC1CF3EE9B8A65FE70`。

## 验证边界

本次通过的是 Windows 环境及自动生成的小型样例；尚未完成 Debian 真机、长时间大文件压力测试、所有 Office 排版与字体组合的验收。文档排版、跨格式元数据、字幕和复杂 PDF 结构仍受各引擎和目标格式约束。

暂停、OCR、PDF 转可编辑 Word、硬件编码及高级 HDR 工作流未开放。LibreOffice 无可靠百分比接口，显示忙碌状态；不会模拟进度。详细功能边界见 README。
