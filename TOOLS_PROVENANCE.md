# 本地验证工具来源

以下工具用于本工作区开发与测试。普通构建不捆绑；完整便携构建将对应运行文件和原许可证复制到 `release/MediaForge/.tools`，排除下载缓存与 MSI 安装文件。LibreOffice 安装介质内 `System64` 的 Visual C++ 运行库同时复制到 `program`，以支持不进行系统安装的本地 DLL 加载。

| 工具 | 来源 | 校验 |
|---|---|---|
| FFmpeg / FFprobe 9.0.2 essentials | https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip （FFmpeg 官方下载页关联的 Windows 构建） | SHA256 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`，与同源 `.sha256` 一致 |
| LibreOffice 26.2.6.3 | https://download.documentfoundation.org/libreoffice/stable/26.2.6/win/x86_64/LibreOffice_26.2.6_Win_x86-64.msi | SHA256 `f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660`，与官方镜像清单一致 |

FFmpeg 解压在 `.tools/ffmpeg/ffmpeg-9.0.2-essentials_build`，随包 GPLv3 LICENSE 已保留。LibreOffice 使用 `msiexec /a /qn` 管理解包到 `.tools/libreoffice`，没有执行系统级软件安装；调用 `program/soffice.com`。MSI 与解包日志保留在 `.tools/downloads`。

应用运行期间不下载这些工具；“安装指引”仅在用户点击时打开官方网站。复制或分发这些二进制前请阅读随包许可和 `THIRD_PARTY_NOTICES.md`。
