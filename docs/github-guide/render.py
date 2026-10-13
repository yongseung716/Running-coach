from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).parent
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
def font(n,bold=False): return ImageFont.truetype(BOLD if bold else FONT,n)
def frame(title,url,step):
 im=Image.new('RGB',(1040,560),'#f6f8fa');d=ImageDraw.Draw(im)
 d.rounded_rectangle((18,18,1022,542),radius=16,fill='white',outline='#d0d7de',width=2)
 d.rounded_rectangle((18,18,1022,69),radius=16,fill='#24292f')
 d.rectangle((19,45,1021,69),fill='#24292f')
 for x,c in [(41,'#f66'),(62,'#fc6'),(83,'#7c8')]: d.ellipse((x,34,x+12,46),fill=c)
 d.text((118,30),url,font=font(14),fill='#d0d7de')
 d.text((54,96),title,font=font(25,True),fill='#1f2328')
 d.text((54,502),f'{step} · 설명용 화면 예시 — 실제 계정의 스크린샷이 아닙니다.',font=font(14),fill='#667085')
 return im,d

def highlight(d,box,number,note=None):
 d.rounded_rectangle(box,radius=9,outline='#e5484d',width=4)
 x,y=box[0]-18,box[1]-16
 d.ellipse((x-4,y-4,x+34,y+34),fill='#e5484d')
 d.text((x+8,y+1),str(number),font=font(19,True),fill='white')
 if note:d.text((box[0],box[3]+12),note,font=font(17,True),fill='#c7363b')

im,d=frame('1. 설치한 앱의 Configure 클릭','github.com/settings/installations',1)
d.rounded_rectangle((54,151,300,465),radius=9,fill='#f6f8fa')
for y,t in [(180,'Applications'),(232,'Installed GitHub Apps'),(289,'Authorized GitHub Apps'),(345,'Authorized OAuth Apps')]:
 if y==232:d.rounded_rectangle((64,y-6,289,y+37),radius=6,fill='#ddf4ff')
 d.text((79,y),t,font=font(15,y==232),fill='#1f2328')
d.text((333,174),'Installed GitHub Apps',font=font(24,True),fill='#1f2328')
d.rounded_rectangle((333,233,969,351),radius=8,outline='#d0d7de',width=2)
d.rounded_rectangle((358,264,402,309),radius=9,fill='#e5edf3');d.text((367,269),'앱',font=font(20,True),fill='#57606a')
d.text((423,255),'설치한 OpenAI / ChatGPT 관련 앱',font=font(19,True),fill='#1f2328')
d.text((423,286),'실제 설치된 앱 이름은 다를 수 있습니다.',font=font(14),fill='#57606a')
d.rounded_rectangle((818,268,944,316),radius=7,fill='#f6f8fa',outline='#d0d7de',width=2)
d.text((835,278),'Configure',font=font(17,True),fill='#24292f')
highlight(d,(806,256,956,328),1,'이 버튼을 누르세요')
im.save(OUT/'step-1.png')

im,d=frame('2. Repository access에서 저장소 선택','github.com/settings/installations/[설치 번호]',2)
d.text((69,155),'Repository access',font=font(24,True),fill='#1f2328')
d.ellipse((71,208,91,228),outline='#8c959f',width=2);d.text((109,202),'All repositories',font=font(18),fill='#57606a')
d.ellipse((71,248,91,268),outline='#0969da',width=2);d.ellipse((76,253,86,263),fill='#0969da')
d.text((109,241),'Only select repositories',font=font(19,True),fill='#1f2328')
highlight(d,(59,235,450,279),2)
d.rounded_rectangle((109,302,860,348),radius=7,outline='#d0d7de',width=2,fill='#f6f8fa')
d.text((128,309),'Select repositories  ▾',font=font(18),fill='#24292f')
d.rounded_rectangle((109,357,860,468),radius=7,outline='#d0d7de',width=2)
d.text((130,369),'검색: Running-couch',font=font(17),fill='#57606a')
d.rectangle((132,414,153,435),fill='#0969da');d.text((134,409),'✓',font=font(20,True),fill='white')
d.text((169,408),'yongseung716 / Running-couch',font=font(21,True),fill='#1f2328')
highlight(d,(121,399,819,449),3)
im.save(OUT/'step-2.png')

im,d=frame('3. 선택된 저장소를 확인하고 Save 클릭','github.com/settings/installations/[설치 번호]',3)
d.text((70,163),'Repository access',font=font(24,True),fill='#1f2328')
d.text((74,217),'●  Only select repositories',font=font(20,True),fill='#1f2328')
d.rounded_rectangle((104,270,908,328),radius=8,fill='#f6f8fa',outline='#d0d7de',width=2)
d.text((129,281),'✓  yongseung716 / Running-couch',font=font(21,True),fill='#1f2328')
d.rounded_rectangle((105,363,245,414),radius=7,fill='#1f883d')
d.text((152,372),'Save',font=font(20,True),fill='white')
highlight(d,(92,350,258,427),4)
d.text((301,366),'저장 후 목록에 Running-couch가 남아 있는지 확인',font=font(18),fill='#57606a')
im.save(OUT/'step-3.png')
