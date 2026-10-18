from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget


class ParamsDialog(QDialog):
    """One shared editor for batch defaults and per-file overrides."""
    def __init__(self, category: str, values: dict, encoders: set[str], parent=None):
        super().__init__(parent)
        self.category = category
        self.setWindowTitle("转换参数 · " + {"video": "视频", "audio": "音频", "image": "图片", "document": "文档", "pdf": "PDF"}[category])
        self.resize(560, 650)
        self.fields = {}
        self.original = dict(values)
        layout = QVBoxLayout(self); layout.setSpacing(14)
        hint = QLabel("参数会在开始前校验；不兼容的编码、容器或流复制组合不会执行。")
        hint.setWordWrap(True); hint.setObjectName("notice"); layout.addWidget(hint)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); self.form = QFormLayout(content); self.form.setVerticalSpacing(13); self.form.setHorizontalSpacing(22)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(content); layout.addWidget(scroll)
        if category == "video":
            self.combo("preset", "场景预设", [("自定义", "custom"), ("网络播放 · H.264 / 1080p", "web"), ("手机观看 · H.264 / 720p", "mobile"), ("高效压缩 · H.265", "compact"), ("流复制 · 不重新编码", "copy")], "custom")
            choices = [("自动选择兼容编码", "auto"), ("流复制（仅兼容时）", "copy")]
            for text, codec, encoder in [("H.264", "h264", "libx264"), ("H.265 / HEVC", "h265", "libx265"), ("VP9", "vp9", "libvpx-vp9"), ("MPEG-4", "mpeg4", "mpeg4")]:
                if encoder in encoders: choices.append((text, codec))
            self.combo("video_codec", "视频编码", choices, "auto")
            audio_choices = [("自动选择兼容编码", "auto"), ("流复制", "copy")]
            for label, codec, encoder in [("AAC", "aac", "aac"), ("MP3", "mp3", "libmp3lame"), ("Opus", "opus", "libopus"), ("Vorbis", "vorbis", "libvorbis"), ("FLAC", "flac", "flac"), ("PCM", "pcm_s16le", "pcm_s16le")]:
                if encoder in encoders: audio_choices.append((label, codec))
            self.combo("audio_codec", "音频编码", audio_choices, "auto")
            self.spin("width", "宽度（0 = 原始）", 0, 16384, 0)
            self.spin("height", "高度（0 = 原始）", 0, 16384, 0)
            self.decimal("fps", "帧率（0 = 原始）", 0, 240, 0, 3)
            self.line("video_bitrate", "视频码率（如 2500k）", "")
            self.line("audio_bitrate", "音频码率（如 192k）", "")
            self.check("remove_audio", "移除所有音轨", False)
            self.line("audio_track", "音轨序号（0 起 / all 全部）", "all")
            self.combo("subtitles", "字幕", [("移除字幕", "remove"), ("复制（容器需兼容）", "copy"), ("转换文本字幕（样式可能变化）", "convert")], "remove")
            self.check("preserve_metadata", "保留可兼容的元数据", True)
            self.fields["preset"].currentIndexChanged.connect(self.preset_changed)
        elif category == "audio":
            hint.setText("MP3、AAC / M4A、OGG、Opus 为有损格式，重新编码可能降低音质。无损格式无法恢复源文件已经丢失的信息。")
            self.line("audio_bitrate", "码率（如 192k，空 = 默认）", "")
            self.combo("sample_rate", "采样率", [("保持原始", 0), ("22,050 Hz", 22050), ("44,100 Hz", 44100), ("48,000 Hz", 48000), ("96,000 Hz", 96000)], 0)
            self.combo("channels", "声道", [("保持原始", 0), ("单声道", 1), ("立体声", 2)], 0)
            self.decimal("volume", "音量倍数（1 = 原始）", 0, 8, 1, 2)
            self.decimal("trim_start", "裁剪起点（秒）", 0, 999999, 0, 3)
            self.decimal("trim_end", "裁剪终点（0 = 完整）", 0, 999999, 0, 3)
            self.spin("audio_track", "提取音轨序号（0 起）", 0, 99, 0)
            self.check("preserve_metadata", "保留支持的标题、作者等元数据", True)
            self.check("preserve_cover", "保留目标格式支持的封面", True)
        elif category == "image":
            hint.setText("JPEG / BMP 不保留透明背景。第一帧模式会丢弃动画；保留多帧仅适用于支持的 GIF、WebP、TIFF。元数据是否可保留取决于输出格式。")
            self.spin("quality", "质量（JPEG / WebP）", 1, 100, 90)
            self.spin("compression", "PNG 压缩等级", 0, 9, 6)
            self.spin("width", "宽度（0 = 原始）", 0, 50000, 0)
            self.spin("height", "高度（0 = 原始）", 0, 50000, 0)
            self.check("keep_aspect", "保持纵横比", True)
            self.combo("rotation", "顺时针旋转", [("不旋转", 0), ("90°", 90), ("180°", 180), ("270°", 270)], 0)
            self.line("background", "透明区域底色", "#FFFFFF")
            self.combo("animation", "多帧图片", [("仅第一帧", "first"), ("保留所有帧", "all")], "first")
            self.check("preserve_metadata", "尽可能保留 EXIF / ICC", True)
        elif category == "document":
            hint.setText("使用 LibreOffice 在本机转换。字体、分页、公式和嵌入对象可能出现差异，请复核输出。PDF 转可编辑 Word / OCR 尚未开放。")
            self.spin("timeout", "单文件超时（秒）", 30, 3600, 180)
            self.line("txt_encoding", "TXT 输入编码", "utf-8")
        else:
            hint.setText("页码从 1 开始。例如 1-3,5；留空表示全部。拆分按每页生成文件，提取按输入顺序生成一个新 PDF。")
            self.line("pages", "页码范围", "")
            self.spin("dpi", "页面转图片分辨率（DPI）", 36, 600, 150)
        for key, widget in self.fields.items():
            if key in values: self.set_value(widget, values[key])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存参数")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def add(self, key, label, widget):
        self.fields[key] = widget; self.form.addRow(label, widget)

    def combo(self, key, label, choices, default):
        w = QComboBox()
        for name, data in choices: w.addItem(name, data)
        w.setCurrentIndex(max(0, w.findData(default))); self.add(key, label, w)

    def line(self, key, label, default):
        self.add(key, label, QLineEdit(str(default)))

    def spin(self, key, label, low, high, default):
        w = QSpinBox(); w.setRange(low, high); w.setValue(default); self.add(key, label, w)

    def decimal(self, key, label, low, high, default, decimals=2):
        w = QDoubleSpinBox(); w.setRange(low, high); w.setDecimals(decimals); w.setValue(default); self.add(key, label, w)

    def check(self, key, label, default):
        w = QCheckBox(label); w.setChecked(default); self.add(key, "", w)

    @staticmethod
    def set_value(widget, value):
        if isinstance(widget, QComboBox):
            idx = widget.findData(value)
            if idx >= 0: widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox): widget.setChecked(bool(value))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): widget.setValue(float(value) if isinstance(widget, QDoubleSpinBox) else int(value))
        else: widget.setText(str(value))

    def values(self):
        data = dict(self.original)
        for key, w in self.fields.items():
            if isinstance(w, QComboBox): data[key] = w.currentData()
            elif isinstance(w, QCheckBox): data[key] = w.isChecked()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)): data[key] = w.value()
            else: data[key] = w.text().strip()
        return data

    def preset_changed(self):
        presets = {"web": {"video_codec": "h264", "width": 1920, "height": 1080, "audio_codec": "aac"}, "mobile": {"video_codec": "h264", "width": 1280, "height": 720, "audio_codec": "aac"}, "compact": {"video_codec": "h265", "width": 0, "height": 0, "audio_codec": "aac"}, "copy": {"video_codec": "copy", "audio_codec": "copy", "width": 0, "height": 0, "fps": 0, "video_bitrate": "", "audio_bitrate": ""}}
        for key, value in presets.get(self.fields["preset"].currentData(), {}).items(): self.set_value(self.fields[key], value)
