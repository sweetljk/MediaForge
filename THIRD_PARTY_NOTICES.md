# 第三方依赖及分发注意事项

MediaForge 项目代码采用 GNU Affero General Public License v3.0（AGPL-3.0-only），完整文本见根目录 LICENSE。第三方组件仍按各自许可证授权。本文件记录依赖与上游许可来源，不替代具体版本随包的许可证和版权声明。发布安装包之前应保存各实际分发组件的许可证，并检查其完整义务。本次 GitHub 发布仅包含项目源码，不上传外部工具二进制或完整便携包。

构建区别：`build.ps1` 的普通构建不包含外部工具；`build-portable.ps1` 的完整便携版包含 FFmpeg / FFprobe、LibreOffice，以及其安装介质附带的 Microsoft Visual C++ 运行库。完整便携版保留工具目录内的许可证、版权说明和 NOTICE，以及 `_internal/licenses`。下表中的“默认不捆绑”指普通构建。保留声明不等于自动满足所有源码提供等分发义务。

| 依赖 | 用途 | 上游许可与要求 |
|---|---|---|
| PySide6 / Qt | 桌面 GUI | LGPLv3 / GPL / 商业许可，具体 Qt 模块各有差异。分发时提供版权许可、必要的库替换与重新链接能力及 LGPL 要求；不要把仅 GPL 的可选模块误作 LGPL。参见 [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html)。 |
| Pillow | 图片 | HPND（Historical Permission Notice and Disclaimer）；保留许可证与版权信息，wheel中的解码库还各有声明。参见 [Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE)。 |
| PyMuPDF / MuPDF | PDF 渲染和检查 | **AGPLv3 或 Artifex 商业许可**。这不是 MIT 库；闭源分发不能忽略此项。按完整许可评估对应源码提供等义务，或取得商业许可。参见 [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)。 |
| pypdf | PDF 页面处理 | BSD-3-Clause，保留声明。参见 [pypdf license](https://github.com/py-pdf/pypdf/blob/main/LICENSE)。 |
| psutil | 子进程树终止 | BSD-3-Clause，保留声明。参见 [psutil license](https://github.com/giampaolo/psutil/blob/master/LICENSE)。 |
| pytest / pytest-qt | 测试 | MIT；仅开发依赖。保留相应许可。 |
| PyInstaller | 构建 | GPLv2-or-later，附有允许生成应用采用自身许可的特殊分发例外；例外不改变所捆绑依赖的许可。参见 [PyInstaller license](https://pyinstaller.org/en/stable/license.html)。 |
| FFmpeg / FFprobe | 外部媒体工具 | 通常 LGPLv2.1-or-later；启用 GPL 组件后构建受 GPL 约束，启用某些 nonfree 选项会限制分发。**本工作区开发测试所用 Gyan essentials 构建随附 GPLv3 LICENSE**。默认不捆绑。参见 [FFmpeg legal](https://ffmpeg.org/legal.html)。 |
| LibreOffice | 外部 Office 工具 | MPL 2.0，第三方组件还有各自许可。默认不捆绑。参见 [LibreOffice licenses](https://www.libreoffice.org/licenses/)。 |
| ImageMagick（可选检测） | 后续扩展 | ImageMagick License；当前无转换功能依赖它。参见 [ImageMagick license](https://imagemagick.org/script/license.php)。 |

FFmpeg 编码器和容器可能还有与软件版权不同的专利问题，按分发和使用地区评估。不要在未核对许可的情况下将 `.tools` 整体加入安装包。Python/Qt wheel 内附带的第三方库应一并保留原版权材料。
