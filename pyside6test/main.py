from qfluentwidgets import NavigationItemPosition, FluentWindow, SubtitleLabel, setFont, HeaderCardWidget,StrongBodyLabel,CaptionLabel,ImageLabel
from qfluentwidgets import FluentIcon as FIF
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QFrame,QHBoxLayout,QWidget,QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


class Widget(QFrame):

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        self.label = SubtitleLabel(text, self)
        self.hBoxLayout = QHBoxLayout(self)

        setFont(self.label, 24)
        self.label.setAlignment(Qt.AlignCenter)
        self.hBoxLayout.addWidget(self.label, 1, Qt.AlignCenter)

        # 必须给子界面设置全局唯一的对象名
        self.setObjectName(text.replace(' ', '-'))

class Homepage(QWidget):

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)        

class AppInfo(HeaderCardWidget):
    '''程序与悬浮窗状态'''

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        self.setTitle('当前状态')
        self.setBorderRadius(8)
        self.game = StrongBodyLabel('游戏')
        self.server = StrongBodyLabel('服务器')
        self.gamestatus = CaptionLabel('等待游戏运行')
        self.serverstatus = CaptionLabel('等待连接游戏服务器')
        self.party = StrongBodyLabel('当前小队')
        self.partyimage1 = ImageLabel('icon_chr_0003_endminf.png')
        self.partyname1 = CaptionLabel('管理员')
        self.partyimage2 = ImageLabel('icon_chr_0003_endminf.png')
        self.partyname2 = CaptionLabel('管理员')
        self.partyimage3 = ImageLabel('icon_chr_0003_endminf.png')
        self.partyname3 = CaptionLabel('管理员')
        self.partyimage4 = ImageLabel('icon_chr_0003_endminf.png')
        self.partyname4 = CaptionLabel('管理员')
        self.gameLayout = QHBoxLayout()
        self.gameLayout.addWidget(self.game,alignment=Qt.AlignmentFlag.AlignLeft)
        self.gameLayout.addWidget(self.gamestatus,alignment=Qt.AlignmentFlag.AlignRight)
        self.serverLayout = QHBoxLayout()
        self.serverLayout.addWidget(self.server,alignment=Qt.AlignmentFlag.AlignLeft)
        self.serverLayout.addWidget(self.serverstatus,alignment=Qt.AlignmentFlag.AlignRight)
        self.partyLayout1 = QHBoxLayout()

class Window(FluentWindow):
    """ 主界面 """

    def __init__(self):
        super().__init__()

        # 创建子界面，实际使用时将 Widget 换成自己的子界面
        self.homeInterface = Widget('Home Interface', self)
        self.musicInterface = Widget('Overlay Interface', self)
        self.settingInterface = Widget('Info Interface', self)
        self.albumInterface = Widget('Battlelog Interface', self)
        self.albumInterface1 = Widget('Sublog Interface 1', self)

        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.homeInterface, FIF.HOME, '主页')
        self.addSubInterface(self.musicInterface, FIF.QUICK_NOTE, '悬浮窗')

        self.navigationInterface.addSeparator()

        self.addSubInterface(self.albumInterface, FIF.ROTATE, '战斗日志', NavigationItemPosition.SCROLL)
        self.addSubInterface(self.albumInterface1, icon='' ,text='战斗1', parent=self.albumInterface)

        self.addSubInterface(self.settingInterface, FIF.INFO, '关于', NavigationItemPosition.BOTTOM)

    def initWindow(self):
        self.resize(900, 700)
        self.setWindowIcon(QIcon('./pyside6/icon.png'))
        self.setWindowTitle('ZMDlogs 战斗分析器')
        self.navigationInterface.setExpandWidth(200)
        self.navigationInterface.setCollapsible(False)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Window()
    w.show()
    app.exec()
