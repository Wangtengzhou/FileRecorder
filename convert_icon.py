from PIL import Image, ImageDraw
import sys

def add_corners(im, rad):
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def convert_to_ico(png_path, ico_path):
    try:
        img = Image.open(png_path).convert("RGBA")
        
        # 处理圆角 (假设图片是1024x1024，圆角半径设为180，这是iOS图标的典型比例)
        # 如果图片本身有白色背景，先不需要去背景，直接切圆角即可，切掉的部分变透明
        # 这里的关键是将圆角以外的区域变透明
        
        # 重新加载 img 以确保干净
        radius = int(min(img.size) * 0.22)  # iOS 图标曲率约为 22%
        
        # 创建圆角蒙版
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
        
        # 应用蒙版
        img.putalpha(mask)
        
        # 保存处理后的 PNG (用于窗口图标)
        img.save(png_path, format='PNG')
        
        # 保存 ICO（包含多种尺寸，最大 512x512）
        # Windows 标准尺寸：16, 24, 32, 48, 64, 128, 256, 512
        img.save(ico_path, format='ICO', sizes=[
            (512, 512), (256, 256), (128, 128), (64, 64), 
            (48, 48), (32, 32), (24, 24), (16, 16)
        ])
        print(f"Successfully converted {png_path} to {ico_path} with rounded corners and high resolution")
    except Exception as e:
        print(f"Error converting image: {e}")
        sys.exit(1)

if __name__ == "__main__":
    convert_to_ico("logo.png", "logo.ico")
