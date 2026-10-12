"""Generate the existing geometric wave brand's icon and compile a WinExe."""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
image = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, 252, 252), radius=58, fill='#009b91')
for y in (83, 128, 173):
    points = [(55, y+4), (70, y-6), (86, y-10), (104, y-4),
              (125, y+8), (146, y+11), (165, y+5), (187, y-8), (201, y-10)]
    draw.line(points, fill='white', width=14, joint='curve')
    for x, cy in (points[0], points[-1]):
        draw.ellipse((x-7,cy-7,x+7,cy+7), fill='white')
icon = ROOT / 'web' / 'app.ico'
image.save(icon, sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.save(ROOT / 'web' / 'app.png')
compiler = Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Windows.Forms.dll',
                '/win32icon:'+str(icon), '/out:'+str(ROOT/'ReupVoiceStudio.exe'),
                str(ROOT/'native'/'Launcher.cs')], check=True)
print(ROOT/'ReupVoiceStudio.exe')
