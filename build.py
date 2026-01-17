import os
import shutil
import subprocess
import sys
from pathlib import Path

def print_step(msg):
    print(f"\n{'='*50}")
    print(f" {msg}")
    print(f"{'='*50}\n")

def clean_build_dirs():
    """清理构建目录"""
    print_step("1. 清理旧构建文件")
    dirs_to_clean = ['build', 'dist']
    for d in dirs_to_clean:
        if os.path.exists(d):
            print(f"正在删除: {d} ...")
            shutil.rmtree(d)
        else:
            print(f"目录不存在，跳过: {d}")

def run_pyinstaller():
    """运行 PyInstaller"""
    print_step("2. 开始打包 (PyInstaller)")
    
    spec_file = "FileRecorder.spec"
    if not os.path.exists(spec_file):
        print(f"错误: 找不到 {spec_file}")
        sys.exit(1)
        
    cmd = [sys.executable, "-m", "PyInstaller", spec_file, "--clean", "--noconfirm"]
    
    try:
        subprocess.check_call(cmd)
        print("PyInstaller 打包成功！")
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        sys.exit(1)

def setup_files():
    """配置文件处理"""
    print_step("3. 处理配置文件")
    
    dist_dir = Path("dist")
    exe_file = dist_dir / "FileRecorder.exe"
    
    if not exe_file.exists():
        print(f"警告: 未找到可执行文件 {exe_file}，跳过配置文件处理")
        return
    
    # 单文件模式下，config.json 应该放在 exe 同目录
    src_config = Path("config.example.json")
    dst_config = dist_dir / "config.json"
    
    if src_config.exists():
        shutil.copy2(src_config, dst_config)
        print(f"已创建默认配置: {dst_config}")
    else:
        print(f"警告: 找不到示例配置 {src_config}")

def main():
    print("开始自动构建 FileRecorder...")
    
    clean_build_dirs()
    run_pyinstaller()
    setup_files()
    
    print_step("构建完成！")
    exe_path = os.path.abspath("dist/FileRecorder.exe")
    print(f"可执行文件位置: {exe_path}")
    print("注意: 已自动生成默认 config.json，无需手动复制。")

if __name__ == "__main__":
    main()

