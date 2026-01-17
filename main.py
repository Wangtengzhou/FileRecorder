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

from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor

from ui.main_window import MainWindow
from config import config


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
    
    # 应用主题
    from ui.theme import theme_manager
    initial_theme = config.get("ui", "theme", default="auto")
    theme_manager.set_mode(initial_theme)
    # 确保应用至少被调用一次以设置颜色（如果是 auto，set_mode 会启动 timer 并立即 check）
    # 但为了确保 set_window_dark_title_bar 生效，我们需要在 show 之后再处理一次，或者这里先 apply 一次给 app
    theme_manager.apply_theme(initial_theme)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 手动触发一次主题应用以确保标题栏颜色正确
    # 因为 apply_theme 会遍历 topLevelWidgets，现在 window 已经显示了
    theme_manager.apply_theme(initial_theme)
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
