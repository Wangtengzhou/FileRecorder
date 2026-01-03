"""
FileRecorder 设置对话框
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QLabel, QGroupBox, QCheckBox, QSpinBox, QTextEdit
)

from config import config


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(500, 400)
        
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
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("输入您的API密钥")
        ai_form.addRow("API 密钥:", self.api_key_input)
        
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("留空使用默认OpenAI地址，或输入自定义地址如 https://api.deepseek.com")
        ai_form.addRow("接口地址:", self.base_url_input)
        
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("如: gpt-4o-mini, deepseek-chat, qwen-turbo")
        ai_form.addRow("模型名称:", self.model_input)
        
        ai_layout.addWidget(ai_group)
        
        # 说明文字
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
        
        # 扫描设置
        self.timeout_spin.setValue(config.get("scanner", "timeout_seconds", default=5))
        self.batch_size_spin.setValue(config.get("scanner", "batch_size", default=1000))
        
        ignore_patterns = config.get("scanner", "ignore_patterns", default=[])
        self.ignore_input.setPlainText("\n".join(ignore_patterns))
        
        # 界面设置
        self.remember_size_check.setChecked(config.get("ui", "remember_window_size", default=True))
    
    def _save_settings(self):
        """保存设置"""
        # AI设置
        config.set("ai", "api_key", value=self.api_key_input.text())
        config.set("ai", "base_url", value=self.base_url_input.text())
        config.set("ai", "model", value=self.model_input.text())
        
        # 扫描设置
        config.set("scanner", "timeout_seconds", value=self.timeout_spin.value())
        config.set("scanner", "batch_size", value=self.batch_size_spin.value())
        
        ignore_text = self.ignore_input.toPlainText()
        ignore_patterns = [p.strip() for p in ignore_text.split('\n') if p.strip()]
        config.set("scanner", "ignore_patterns", value=ignore_patterns)
        
        # 界面设置
        config.set("ui", "remember_window_size", value=self.remember_size_check.isChecked())
        
        self.accept()
