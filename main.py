"""
FileRecorder - 智能文件索引助手
程序入口
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow


def main():
    """主函数"""
    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用 Fusion 风格，跨平台一致
    
    # 设置应用信息
    app.setApplicationName("FileRecorder")
    app.setApplicationDisplayName("FileRecorder - 智能文件索引助手")
    app.setOrganizationName("FileRecorder")
    
    # 修复 Fusion 风格复选框蓝色背景问题
    app.setStyleSheet("""
        QCheckBox::indicator:unchecked {
            background-color: transparent;
            border: 1px solid #888888;
        }
    """)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
