# 开发说明

## 目录

```text
mediaforge/
  app.py / __main__.py       Qt 入口、生命周期
  worker.py                 无界面子进程及实际事件协议
  ui/                       页面、参数、主题、图标、国际化入口
  core/                     Job 模型、错误、格式路由
  converters/               视频音频、图片、文档、PDF 业务
  engines/                  唯一进程网关、FFmpeg、LibreOffice、原生隔离
  jobs/                     与 Qt 无关的队列及事务输出发布
  services/                 工具检测、文件信息、设置、SQLite历史
  utils/                    输出命名、可写性、空间和复制
tests/                      单测、真实引擎转换及UI联调
```

## 转换器契约

`convert(job, output, context) -> list[Path]`。`output` 属于任务私有临时目录；转换器不得修改原始文件或直接发布到最终目录。返回所有经过验证的输出文件。

`context.progress(value, message)` 的 value 为 **0–100 或 None**。None 表示引擎不提供可测百分比；不能用计时器递增百分比。只有任务管理器验证和发布成功后才显示 100%。外部工具通过 `context.run(argv)` 调用，可取消、超时并保留错误日志。不要在 UI 使用 subprocess。

新增格式需更新 `core.formats`、对应转换器的兼容矩阵、参数界面和实际转换测试。新增外部工具在 `services.tools` 注册，不能仅根据扩展名宣称支持。

## 并发与退出

JobManager 使用最多 3 个 worker，默认调度 1 项。UI 通过 Qt Signal 转发后台事件。图片、PDF、文档工作委托独立进程，事件记录在任务临时目录，兼容无控制台的 PyInstaller 产物。取消通过进程树终止实现；输出提交边界之后的取消按完成处理，以保证结果完整。原生库不共享线程访问。

历史是完成快照；运行队列在内存中。未来可增加重启恢复，但不得将崩溃中断任务自动标为成功。任务移除不删除输出和历史。

## 已知设计边界

输出发布锁覆盖本进程内所有队列任务；其他进程同名创建通过排他文件操作保护。POSIX/NTFS 优先用硬链接提交，再移除私有临时副本；不支持链接的文件系统采用排他创建并在失败时回滚。覆盖策略保留旧文件备份直到全部输出发布完成。

当前无自动旧临时目录清理，避免误删用户目录或仍在运行任务。扩展清理时必须验证所有权标记、绝对路径、存活进程和创建时间，禁止盲目递归删除用户配置目录。

## 测试

测试使用 pytest/pytest-qt，源码根目录运行 `python -m pytest`。真实外部工具用缺少依赖时显式 skip，不能以 stub 的通过代替引擎实测。GUI 测试可用 `QT_QPA_PLATFORM=offscreen`；窗口真实显示另外验收。所有集成文件在 pytest tmp_path 创建。

## Windows 完整便携构建

`build-portable.ps1` 调用 `scripts/package_portable.py`，在 `release` 中独立构建，不覆盖原 `dist`。它复制外部引擎及许可证，将 LibreOffice 安装介质中 x64 VC 运行库放到程序同目录，排除 MSI 和下载缓存，验证真实转换后生成 ZIP 与 SHA256。

`scripts/verify_package.py --portable --executable <EXE> --area <测试目录>` 使用空工具配置、仅含 System32 的 PATH、不同工作目录，验证 EXE 自动检测工具。`scripts/verify_portable_archive.py` 进一步检查 ZIP CRC、解压到另一个中文及空格目录，再执行上述验证。测试不会调用 VBS，不会修改用户设置；检查用设置存放在测试目录。

自动检测路径由 EXE 位置确定；手动配置和显式环境变量仍优先。不要把自动发现的引擎绝对路径永久写入设置，否则移动便携目录后会产生失效路径。

## 参考接口

- [FFmpeg 进度、流选择和编解码参数](https://ffmpeg.org/ffmpeg.html)
- [LibreOffice 命令行与用户配置参数](https://help.libreoffice.org/latest/en-GB/text/shared/guide/start_parameters.html)
- [Qt 跨线程信号](https://doc.qt.io/qtforpython-6/examples/example_widgets_thread_signals.html)
- [PyMuPDF 多进程说明](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html)
