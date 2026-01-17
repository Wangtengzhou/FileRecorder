"""
FileRecorder 设置对话框
"""
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLineEdit, QPushButton, QTabWidget, QWidget, QScrollArea, QFrame,
    QLabel, QGroupBox, QCheckBox, QSpinBox, QTextEdit, QSizePolicy
)

from config import config
from ai.client import test_api_connection

# 默认内置标签（用户可删除和恢复）
DEFAULT_TAGS = ["电影", "电视剧", "动漫", "纪录片", "综艺", "NSFW", "其他"]


class ApiTestThread(QThread):
    """API 检测线程"""
    finished = Signal(bool, str)  # 成功, 消息
    
    def __init__(self, api_key, base_url, model):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    def run(self):
        success, msg = test_api_connection(self.api_key, self.base_url, self.model)
        self.finished.emit(success, msg)


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(500, 400)
        
        self._test_thread = None
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 标签页
        tabs = QTabWidget()
        
        # AI 设置页
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        
        ai_group = QGroupBox("AI接口配置")
        ai_form = QFormLayout(ai_group)
        
        # API 密钥行（带检测按钮和显示/隐藏按钮）
        api_key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("输入您的API密钥")
        api_key_layout.addWidget(self.api_key_input)
        
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(30)
        self.show_key_btn.setToolTip("显示/隐藏密钥")
        self.show_key_btn.clicked.connect(self._toggle_key_visibility)
        api_key_layout.addWidget(self.show_key_btn)
        
        self.test_btn = QPushButton("检测")
        self.test_btn.setFixedWidth(80)
        self.test_btn.clicked.connect(self._on_test_api)
        api_key_layout.addWidget(self.test_btn)
        
        api_key_widget = QWidget()
        api_key_widget.setLayout(api_key_layout)
        ai_form.addRow("API 密钥:", api_key_widget)
        
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("留空使用默认OpenAI地址，或输入自定义地址如 https://api.deepseek.com")
        self.base_url_input.textChanged.connect(self._update_api_preview)
        ai_form.addRow("接口地址:", self.base_url_input)
        
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("如: gpt-4o-mini, deepseek-chat, qwen-turbo")
        ai_form.addRow("模型名称:", self.model_input)
        
        ai_layout.addWidget(ai_group)
        
        # AI 参数设置
        param_group = QGroupBox("AI 参数设置")
        param_form = QFormLayout(param_group)
        
        # Temperature
        self.temperature_spin = QSpinBox()
        self.temperature_spin.setRange(0, 20)  # 0-2.0，显示为整数（实际除以10）
        self.temperature_spin.setValue(1)  # 默认 0.1
        self.temperature_spin.setToolTip(
            "Temperature 参数（0-20 对应 0.0-2.0）\n\n"
            "• 0-2：非常确定，结果高度一致（推荐用于分类任务）\n"
            "• 3-7：平衡模式\n"
            "• 8-20：更有创造性，结果变化大\n\n"
            "默认值：1（即 0.1），适合分类识别任务"
        )
        param_form.addRow("Temperature (×0.1):", self.temperature_spin)
        
        ai_layout.addWidget(param_group)
        
        # API 限流设置
        rate_group = QGroupBox("API 限流设置")
        rate_form = QFormLayout(rate_group)
        
        self.tpm_spin = QSpinBox()
        self.tpm_spin.setRange(1000, 1000000)
        self.tpm_spin.setSingleStep(10000)
        self.tpm_spin.setValue(60000)
        self.tpm_spin.setToolTip(
            "每分钟最大令牌数（Tokens Per Minute）\n\n"
            "• OpenAI GPT-4o-mini: 200,000\n"
            "• DeepSeek: 根据套餐不同\n"
            "• 通义千问: 根据模型不同\n\n"
            "设置过高可能导致 429 错误（速率限制）"
        )
        rate_form.addRow("TPM 限制:", self.tpm_spin)
        
        self.rpm_spin = QSpinBox()
        self.rpm_spin.setRange(1, 1000)
        self.rpm_spin.setValue(60)
        self.rpm_spin.setToolTip(
            "每分钟最大请求数（Requests Per Minute）\n\n"
            "• 免费账户通常较低（3-20）\n"
            "• 付费账户通常较高（60-500）\n\n"
            "建议根据 API 服务商的限制设置"
        )
        rate_form.addRow("RPM 限制:", self.rpm_spin)
        
        self.batch_delay_spin = QSpinBox()
        self.batch_delay_spin.setRange(0, 10000)
        self.batch_delay_spin.setSingleStep(100)
        self.batch_delay_spin.setValue(500)
        self.batch_delay_spin.setSuffix(" ms")
        self.batch_delay_spin.setToolTip(
            "每批次处理后的等待时间（毫秒）\n\n"
            "• 0：无延迟（适合高配额账户）\n"
            "• 500-1000：推荐值，避免速率限制\n"
            "• 2000+：保守设置，适合免费账户\n\n"
            "如果频繁遇到 429 错误，请增加此值"
        )
        rate_form.addRow("批次延迟:", self.batch_delay_spin)
        
        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(10, 300)
        self.api_timeout_spin.setValue(60)
        self.api_timeout_spin.setSuffix(" 秒")
        self.api_timeout_spin.setToolTip(
            "单次 API 请求的超时时间\n\n"
            "• 30-60：推荐值\n"
            "• 120+：适合大批量请求或网络较慢的情况"
        )
        rate_form.addRow("请求超时:", self.api_timeout_spin)
        
        ai_layout.addWidget(rate_group)
        
        # 预览和说明文字
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet("color: #0066cc; font-size: 11px;")
        self.preview_label.setWordWrap(True)
        self._update_api_preview()  # 初始化预览
        ai_layout.addWidget(self.preview_label)
        
        note_label = QLabel(
            "提示：本软件使用OpenAI兼容格式接口，支持以下服务：\n"
            "• OpenAI: 留空接口地址\n"
            "• DeepSeek: https://api.deepseek.com\n"
            "• 通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            "• 其他兼容OpenAI格式的服务"
        )
        note_label.setStyleSheet("color: gray; font-size: 11px;")
        note_label.setWordWrap(True)
        ai_layout.addWidget(note_label)
        
        ai_layout.addStretch()
        tabs.addTab(ai_tab, "AI接口")
        
        # 扫描设置页
        scan_tab = QWidget()
        scan_layout = QVBoxLayout(scan_tab)
        
        scan_group = QGroupBox("扫描设置")
        scan_form = QFormLayout(scan_group)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" 秒")
        scan_form.addRow("网络路径超时:", self.timeout_spin)
        
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(100, 10000)
        self.batch_size_spin.setSingleStep(100)
        scan_form.addRow("批量插入大小:", self.batch_size_spin)
        
        scan_layout.addWidget(scan_group)
        
        # 忽略模式
        ignore_group = QGroupBox("忽略模式（每行一个）")
        ignore_layout = QVBoxLayout(ignore_group)
        self.ignore_input = QTextEdit()
        self.ignore_input.setMaximumHeight(100)
        ignore_layout.addWidget(self.ignore_input)
        scan_layout.addWidget(ignore_group)
        
        scan_layout.addStretch()
        tabs.addTab(scan_tab, "扫描")
        
        # 界面设置页
        ui_tab = QWidget()
        ui_layout = QVBoxLayout(ui_tab)
        
        ui_group = QGroupBox("界面设置")
        ui_form = QFormLayout(ui_group)
        
        self.remember_size_check = QCheckBox("记住窗口大小")
        ui_form.addRow("", self.remember_size_check)
        
        ui_layout.addWidget(ui_group)
        ui_layout.addStretch()
        tabs.addTab(ui_tab, "界面")
        
        # AI 提示词设置页
        prompt_tab = QWidget()
        prompt_layout = QVBoxLayout(prompt_tab)
        
        preset_group = QGroupBox("系统预设提示词")
        preset_layout = QVBoxLayout(preset_group)
        
        preset_note = QLabel(
            "此提示词会自动添加到每次 AI 识别请求中，无需每次手动输入。\n"
            "可用于设置固定的分类规则或矫正规则。"
        )
        preset_note.setStyleSheet("color: gray; font-size: 11px;")
        preset_note.setWordWrap(True)
        preset_layout.addWidget(preset_note)
        
        self.system_preset_input = QTextEdit()
        self.system_preset_input.setPlaceholderText(
            "示例：\n"
            "• 日本目录的都分类为 NSFW AV\n"
            "• 中国目录的都分类为 NSFW 国产\n"
            "• 4K 内容优先保留"
        )
        self.system_preset_input.setMaximumHeight(120)
        preset_layout.addWidget(self.system_preset_input)
        
        prompt_layout.addWidget(preset_group)
        
        # 说明
        prompt_help = QLabel(
            "提示词层级说明：\n\n"
            "1. 系统预设（本页配置）- 固定规则，每次自动添加\n"
            "2. 用户临时提示（AI整理弹窗输入）- 临时规则，当次有效\n\n"
            "两者会合并发送给 AI，系统预设优先级较高。"
        )
        prompt_help.setStyleSheet("color: #666; font-size: 11px;")
        prompt_help.setWordWrap(True)
        prompt_layout.addWidget(prompt_help)
        
        prompt_layout.addStretch()
        tabs.addTab(prompt_tab, "AI提示词")
        
        # 常规设置页
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        
        # 关闭行为设置
        close_group = QGroupBox("关闭行为")
        close_layout = QVBoxLayout(close_group)
        
        close_label = QLabel("点击关闭按钮时：")
        close_layout.addWidget(close_label)
        
        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        
        self.close_btn_group = QButtonGroup(self)
        
        self.close_ask_radio = QRadioButton("每次询问")
        self.close_tray_radio = QRadioButton("最小化到系统托盘")
        self.close_exit_radio = QRadioButton("直接退出程序")
        
        self.close_btn_group.addButton(self.close_ask_radio, 0)
        self.close_btn_group.addButton(self.close_tray_radio, 1)
        self.close_btn_group.addButton(self.close_exit_radio, 2)
        
        close_layout.addWidget(self.close_ask_radio)
        close_layout.addWidget(self.close_tray_radio)
        close_layout.addWidget(self.close_exit_radio)
        
        general_layout.addWidget(close_group)
        general_layout.addStretch()
        
        tabs.addTab(general_tab, "常规")
        
        layout.addWidget(tabs)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_settings)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_settings(self):
        """加载当前设置"""
        # AI设置
        self.api_key_input.setText(config.get("ai", "api_key", default=""))
        self.base_url_input.setText(config.get("ai", "base_url", default=""))
        self.model_input.setText(config.get("ai", "model", default="gpt-4o-mini"))
        
        # AI 参数
        # temperature 存储为 0.1 这样的小数，UI 显示为 1（需要乘10）
        temp_value = config.get("ai", "temperature", default=0.1)
        self.temperature_spin.setValue(int(temp_value * 10))
        
        # 限流设置
        self.tpm_spin.setValue(config.get("ai", "tpm_limit", default=60000))
        self.rpm_spin.setValue(config.get("ai", "rpm_limit", default=60))
        self.batch_delay_spin.setValue(config.get("ai", "batch_delay_ms", default=500))
        self.api_timeout_spin.setValue(config.get("ai", "timeout", default=60))
        
        # 扫描设置
        self.timeout_spin.setValue(config.get("scanner", "timeout_seconds", default=5))
        self.batch_size_spin.setValue(config.get("scanner", "batch_size", default=1000))
        
        ignore_patterns = config.get("scanner", "ignore_patterns", default=[])
        self.ignore_input.setPlainText("\n".join(ignore_patterns))
        
        # 界面设置
        self.remember_size_check.setChecked(config.get("ui", "remember_window_size", default=True))
        
        # AI 提示词设置
        self.system_preset_input.setPlainText(config.get("ai", "system_preset", default=""))
        
        # 关闭行为设置
        close_to_tray = config.get("ui", "close_to_tray")
        remembered = config.get("ui", "close_behavior_remembered", default=False)
        
        if not remembered or close_to_tray is None:
            self.close_ask_radio.setChecked(True)
        elif close_to_tray:
            self.close_tray_radio.setChecked(True)
        else:
            self.close_exit_radio.setChecked(True)
    
    def _save_settings(self):
        """保存设置"""
        # AI设置
        config.set("ai", "api_key", value=self.api_key_input.text())
        config.set("ai", "base_url", value=self.base_url_input.text())
        config.set("ai", "model", value=self.model_input.text())
        
        # AI 参数（UI 显示为 1，存储为 0.1）
        config.set("ai", "temperature", value=self.temperature_spin.value() / 10.0)
        
        # 限流设置
        config.set("ai", "tpm_limit", value=self.tpm_spin.value())
        config.set("ai", "rpm_limit", value=self.rpm_spin.value())
        config.set("ai", "batch_delay_ms", value=self.batch_delay_spin.value())
        
        # AI 提示词设置
        config.set("ai", "system_preset", value=self.system_preset_input.toPlainText())
        config.set("ai", "timeout", value=self.api_timeout_spin.value())
        
        # 扫描设置
        config.set("scanner", "timeout_seconds", value=self.timeout_spin.value())
        config.set("scanner", "batch_size", value=self.batch_size_spin.value())
        
        ignore_text = self.ignore_input.toPlainText()
        ignore_patterns = [p.strip() for p in ignore_text.split('\n') if p.strip()]
        config.set("scanner", "ignore_patterns", value=ignore_patterns)
        
        # 界面设置
        config.set("ui", "remember_window_size", value=self.remember_size_check.isChecked())
        
        # 关闭行为设置
        checked_id = self.close_btn_group.checkedId()
        if checked_id == 0:
            # 每次询问
            config.set("ui", "close_to_tray", value=None)
            config.set("ui", "close_behavior_remembered", value=False)
        elif checked_id == 1:
            # 最小化到托盘
            config.set("ui", "close_to_tray", value=True)
            config.set("ui", "close_behavior_remembered", value=True)
        else:
            # 直接退出
            config.set("ui", "close_to_tray", value=False)
            config.set("ui", "close_behavior_remembered", value=True)
        
        config.save()
        self.accept()
    
    def _on_test_api(self):
        """点击检测按钮"""
        api_key = self.api_key_input.text().strip()
        base_url = self.base_url_input.text().strip()
        model = self.model_input.text().strip() or "gpt-4o-mini"
        
        if not api_key:
            self._show_test_result(False, "请先输入 API 密钥")
            return
        
        # 显示加载状态
        self.test_btn.setText("⏳")
        self.test_btn.setEnabled(False)
        self.test_btn.setStyleSheet("")
        
        # 启动后台线程
        self._test_thread = ApiTestThread(api_key, base_url, model)
        self._test_thread.finished.connect(self._on_test_finished)
        self._test_thread.start()
    
    def _on_test_finished(self, success: bool, msg: str):
        """API 检测完成"""
        self._show_test_result(success, msg)
    
    def _show_test_result(self, success: bool, msg: str):
        """显示检测结果"""
        self.test_btn.setEnabled(True)
        
        if success:
            self.test_btn.setText("✓ 成功")
            self.test_btn.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.test_btn.setText("✗ 失败")
            self.test_btn.setStyleSheet("color: red; font-weight: bold;")
            self.test_btn.setToolTip(msg)
        
        # 3秒后恢复按钮状态
        # 5秒后恢复按钮状态
        QTimer.singleShot(5000, self._reset_test_btn)
    
    def _reset_test_btn(self):
        """恢复检测按钮状态"""
        self.test_btn.setText("检测")
        self.test_btn.setStyleSheet("")
        self.test_btn.setToolTip("")
    
    def _toggle_key_visibility(self):
        """切换 API 密钥显示/隐藏"""
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.show_key_btn.setText("🙈")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.show_key_btn.setText("👁")
    
    def _update_api_preview(self):
        """更新 API 地址预览"""
        base_url = self.base_url_input.text().strip()
        if not base_url:
            base_url = "https://api.openai.com/v1"
        base_url = base_url.rstrip("/")
        full_url = f"{base_url}/chat/completions"
        self.preview_label.setText(f"实际请求地址: {full_url}")

