#-*- coding: utf-8 -*-
import os, sys, logging

import pathlib, glob, time, math, threading, json, copy, webbrowser
from functools import partial
import numpy as np
from itertools import chain

from kivy.config import Config
#Config.set('graphics', 'width', '1024')
#Config.set('graphics', 'height', '768')
from kivy.app import App
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty, BooleanProperty, ListProperty, ObjectProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.modules import keybinding

from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import Image
from kivy.uix.video import Video
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.screenmanager import Screen, FallOutTransition, SlideTransition, RiseInTransition
from kivy.uix.tabbedpanel import TabbedPanelItem, TabbedPanelHeader
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner

import fonts_ja
import databasemanager

#logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'config', 'logging.conf'))
class YesNoPopUp(BoxLayout):
    """ポップアップのコンテンツ部分
 
    YesNoPopUp(yes=self.yes1, no=self.no, text='popup1')
    のように使い、Yesボタン、Noボタンと紐づけたい関数を渡し、textには表示したい文字列を渡してください。
    """
    text = StringProperty()
    subtext = StringProperty()
    yes = ObjectProperty(None)
    no = ObjectProperty(None)

class SimplePopUp(BoxLayout):
    text = StringProperty()
    close = ObjectProperty(None)

class ProgressPopUp(BoxLayout):
    pass

class DBItem(BoxLayout):
    title = StringProperty()
    filenum = NumericProperty()
    is_favorite = BooleanProperty()
    #fa_source = 'data/icons/star.png'

class JumpPopUp(BoxLayout):
    pass

class FilterItem(BoxLayout):
    text = StringProperty()

class TagEditItem(BoxLayout):
    text = StringProperty()

class ThumbnailJump(Button):
    pass
    
class ImageButton(ButtonBehavior, Image):
    pass


class NewEntryLayout(BoxLayout):
    pass

class TagEditLayout(BoxLayout):
    title = StringProperty()

class DataBaseScreen(Screen):
    fullscreen = BooleanProperty(True)

    def add_widget(self, *args):
        if 'content' in self.ids:
            return self.ids.content.add_widget(*args)
        return super(DataBaseScreen, self).add_widget(*args)


class MyDataBaseApp(App):

    # TODO : ログ設定の記述の簡略化
    # kivy側でloggerを使っているっぽいのでクラス単位でloggerを用意する
    APP_LOG_LEVEL = logging.DEBUG
    APP_LOG_FILE = os.path.join(os.path.dirname(__file__), 'app.log')
    APP_LOG_FORMATTER = '[%(levelname)s] %(asctime)s | %(thread)d | %(filename)s(l.%(lineno)d):%(funcName)s | %(message)s'

    logger = logging.getLogger('MyDBApp') # ログの出力名を設定
    logger.setLevel(APP_LOG_LEVEL) # ログレベルの設定
    formatter = logging.Formatter(APP_LOG_FORMATTER) # ログの出力形式の設定

    fh = logging.FileHandler(APP_LOG_FILE) # ログのファイル出力先を設定
    logger.addHandler(fh)
    fh.setFormatter(formatter)
    #sh = logging.StreamHandler() # ログのコンソール出力の設定
    #logger.addHandler(sh)
    #sh.setFormatter(formatter)
    
    curdir = os.path.dirname(__file__)

    NO_IMAGE = StringProperty()
    
    max_thumnail = 50 # 配置する最大サムネイル数
    max_jump_button = 9 # 配置するジャンプボタン数
    animation_speed = .4
    allow_stretch = True

    screen_title = StringProperty()
    hide_menu = BooleanProperty(False)

    # 読み込んだ画像全体の情報
    data_title = StringProperty()
    image_dir = StringProperty()
    image_list = ListProperty([]) # 読み込んでいる画像ファイルの絶対パス
    image_num = NumericProperty()

    image_selected = []
    image_option = {
        'favorite':[],
        'chapter':[]
    }

    item_select_mode = 'normal' # normal:画像ビューへ, trash:ゴミ箱, favorite:お気に入り選択、chapter:チャプター選択
    image_filter_mode = None

    range_selectable = False
    range_select_base = None
    view_size = NumericProperty()

    image_view_index = []
    image_view_num = NumericProperty()
    divided_num = NumericProperty()
    divided_index = None
    divided_slice = ListProperty([0,0])
    thumbnail_num  = 0

    loading_screen = False
    loading_thumbnail = False
    load_cancel = False

    popup_mode = 'close'
    op_is_active = False
    task_remain = False
    entry_count = 0

    db_view_mode = 'Title'
    
    # image_view用
    image_idx = NumericProperty()
    image_file_name = StringProperty()
    image_file_path = StringProperty()

    # ファイルコピーの進捗
    now_title = StringProperty()
    now_task = NumericProperty()
    task_num = NumericProperty()
    task_copied_file = NumericProperty()
    task_file_num = NumericProperty()
    task_progress = NumericProperty()

    # フィルター用情報
    db_filter = {
        'options':{},
        'enable_or':False,
        'init_chars':[],
        'is_favorite':False
    }
    ic_filter_map = {
        'あ':['あ','い','う','え','お'],
        'か':['か','き','く','け','こ'],
        'さ':['さ','し','す','せ','そ'],
        'た':['た','ち','つ','て','と'],
        'な':['な','に','ぬ','ね','の'],
        'は':['は','ひ','ふ','へ','ほ'],
        'ま':['ま','み','む','め','も'],
        'や':['や','ゆ','よ'],
        'ら':['ら','り','る','れ','ろ'],
        'わ':['わ','を','ん'],
        '他':['他']
    }

    # thread
    threads = {}

    def __del__(self):
        self.logger.debug('---------END MyDataBaseApp--------')

    def build(self):

        self.logger.debug('---------Start MyDataBaseApp--------')
        #logging.debug('Start MyDataBaseApp')

        self.title = 'MyDataBase'
        self.view_size = 1

        self.NO_IMAGE = 'data/noimage.png'

        Window.bind(on_dropfile = self._on_drop_files)

        sm = self.root.ids.sm

        # DataBaseItemsViewのテンプレート読み込み
        sm.add_widget(self._load_template('DataBaseItemsView'))
        
        # ThumbnailViewのテンプレート読み込み
        sm.add_widget(self._load_template('ThumbnailView'))
        self.threads['load_thumbnails'] = threading.Thread()

        # ImageViewのテンプレート読み込み
        sm.add_widget(self._load_template('ImageView'))


        # 頭文字選択用のレイアウトの作成
        sip_layout = self._load_template('SelectInitial')
        char_list = [
            ['あ','い','う','え','お'],
            ['か','き','く','け','こ'],
            ['さ','し','す','せ','そ'],
            ['た','ち','つ','て','と'],
            ['な','に','ぬ','ね','の'],
            ['は','ひ','ふ','へ','ほ'],
            ['ま','み','む','め','も'],
            ['や','ゆ','よ'],
            ['ら','り','る','れ','ろ'],
            ['わ','を','ん'],
            ['他']]
        btn_space = 5
        btn_size = 40
        for cl in char_list:
            tmp_size = ((len(cl) * btn_size) + (len(cl)-1) * btn_space, btn_size)
            tmp_layout = BoxLayout(size_hint=(None,None), size=tmp_size)
            for c in cl:
                tmp_btn = Button(text=c)
                tmp_btn.bind(on_release=self.set_initial_character)
                tmp_layout.add_widget(tmp_btn)
            sip_layout.ids.ic.add_widget(tmp_layout)
        self.ic_popup = Popup(title='頭文字選択', content=sip_layout, size_hint=(None, None), size=(700, 300), auto_dismiss=True)
        #self.ic_popup = Popup(title='頭文字選択', content=sip_layout, auto_dismiss=True)

        # キーボードバインディング
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self.root, 'text')
        if self._keyboard.widget:
            # If it exists, this widget is a VKeyboard object which you can use
            # to change the keyboard layout.
            pass
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

        #self.go_databaseitemsview()

    def close_popup(self):
        self.popup.dismiss()
        self.popup_mode = 'close'

    def close_confirm_popup(self):
        
        if self.task_remain:
            self.dbm.resolve_sql_tasks()
            self.reload_db_items()

            sm = self.root.ids.sm
            if sm.current is 'ThumbnailView':
                self.reload_data()
                self.reload_thumbnailview()
            
            self.task_remain = False
        
        self.c_popup.dismiss()

    def select_initial(self, ic_btn):
        self.ic_btn = ic_btn
        self.ic_popup.open()

    def set_initial_character(self, instance):
        """
        content = self.popup.content

        if self.op_is_active:
            content.ids.tp.current_tab.content.ids.ic_btn.text = instance.text
        else:
            content.ids.ic_btn.text = instance.text
        """
        self.ic_btn.text = instance.text
        
        self.ic_popup.dismiss()


    def change_mode(self, mode):

        self.item_select_mode = mode
        self.range_selectable = False

        if self.root.ids.sm.current is 'DataBaseItemsView':
            option_layout = self.root.ids.additional_option
            
            if mode == 'normal':
                height = 0
                option_layout.clear_widgets()
            elif mode == 'trash':
                height = 40
                option_layout.clear_widgets()
                tmp_button = Button(text='削除',size_hint_x=None,width=80, background_color=[0.128, 0.128, 0.128, 1])
                tmp_button.bind(on_release=self.delete_db_items)
                option_layout.add_widget(tmp_button)
            elif mode == 'tag':
                height = 40
                option_layout.clear_widgets()

                tmp_button = Button(text='タグ登録',size_hint_x=None,width=80, background_color=[0.128, 0.128, 0.128, 1])
                tmp_button.bind(on_release=self.open_tag_setting)
                option_layout.add_widget(tmp_button)

                tmp_button2 = Button(text='CSV出力',size_hint_x=None,width=90, background_color=[0.128, 0.128, 0.128, 1])
                #tmp_button2.bind(on_release=self.open_tag_setting)
                option_layout.add_widget(tmp_button2)

                tmp_button3 = Button(text='CSV読込み',size_hint_x=None,width=100, background_color=[0.128, 0.128, 0.128, 1])
                #tmp_button3.bind(on_release=self.open_tag_setting)
                option_layout.add_widget(tmp_button3)

            elif mode == 'favorite':
                height = 40
                option_layout.clear_widgets()
                tmp_txt = 'フィルタOFF' if self.db_filter['is_favorite'] else 'フィルタON'
                tmp_button = ToggleButton(text=tmp_txt,size_hint_x=None,width=120, background_color=[0.128, 0.128, 0.128, 1])
                tmp_button.state = 'down' if self.db_filter['is_favorite'] else 'normal'
                tmp_button.bind(on_release=self.chage_db_mode_favorite)
                option_layout.add_widget(tmp_button)
            else:
                height = 0
                option_layout.clear_widgets()

            Animation(height=height, d=.3, t='out_quart').start(option_layout)

        elif self.root.ids.sm.current is 'ThumbnailView':
            option_layout = self.root.ids.additional_option
            
            if mode == 'normal':
                self.image_selected[:] = False
                height = 0
                option_layout.clear_widgets()
                self._update_all_thumbnail_color()
            else:
                height = 40
                option_layout.clear_widgets()
                range_button = ToggleButton(text='範囲選択',size_hint_x=None,width=90, background_color=[0.128, 0.128, 0.128, 1], state='normal', background_down='atlas://data/images/defaulttheme/action_item_down')
                range_button.bind(on_release=self.change_range_option)
                option_layout.add_widget(range_button)

                if mode == 'trash':
                    tmp_button = Button(text='削除',size_hint_x=None,width=80, background_color=[0.128, 0.128, 0.128, 1])
                    tmp_button.bind(on_release=self.delete_images)
                    option_layout.add_widget(tmp_button)

            Animation(height=height, d=.3, t='out_quart').start(option_layout)


    def go_previous_screen(self):

        sm = self.root.ids.sm
        if sm.current == 'ThumbnailView':
            self.screen_title = 'データベース内容'
            self._wait_cancel()
            sm.transition = SlideTransition(direction='right', duration=self.animation_speed)
            sm.current = 'DataBaseItemsView'
            self._reset_mode()
            return

        if sm.current == 'ImageView':
            self.screen_title = 'サムネイルビュー'
            if self.hide_menu:
                self.change_view_fullscreen()
            sm.transition = SlideTransition(direction='right', duration=self.animation_speed)
            sm.current = 'ThumbnailView'
            self._reset_mode()
            return


    # フィルタ機能
    def open_filter_popup(self):

        sm = self.root.ids.sm

        if sm.current in ['ImageView']:
            return

        #ポップアップ構造のテンプレート読み込み
        content = self._load_template('FilterPopUp')
        tp = content.ids.tp
        tp.clear_tabs()

        # テスト用
        if sm.current is 'InitialScreen':

            db_component = {}
            db_component['ジャンル'] = ['カテゴリ{}'.format(i) for i in range(60)]
            db_component['属性'] = ['タイプ{}'.format(i) for i in range(50)]

            for key, val_list in db_component.items():
                #tp_item = TabbedPanelItem(text=key)
                th = TabbedPanelHeader(text=key)
                filter_items = self._load_template('FilterItems')
                for val in val_list:
                    #print('{0} - {1}'.format(key, val))
                    filter_items.ids.fi.add_widget(FilterItem(text=val))
                    #filter_items.add_widget(FilterItem(text=val))
                th.content = filter_items
                tp.add_widget(th)

        elif sm.current is 'DataBaseItemsView':

            tag_list = {}
            for key in sorted(self.db_tags.keys()):
                tag_list[key] = self.dbm.get_tag_items(key, 'Name', convert=True)

            for key, val_list in sorted(tag_list.items(), key=lambda x:x[0]):
                #tp_item = TabbedPanelItem(text=key)
                th = TabbedPanelHeader(text=key)
                filter_items = self._load_template('FilterItems')
                for val in val_list:
                    #print('{0} - {1}'.format(key, val))
                    filter_items.ids.fi.add_widget(FilterItem(text=val))
                    #filter_items.add_widget(FilterItem(text=val))
                th.content = filter_items
                tp.add_widget(th)

        elif sm.current is 'ThumbnailView':
            th = TabbedPanelHeader(text='その他')
            filter_items = self._load_template('FilterItems')
            filter_items.ids.fi.add_widget(FilterItem(text='お気に入り'))
            filter_items.ids.fi.add_widget(FilterItem(text='チャプター'))
            th.content = filter_items
            tp.add_widget(th)

        self.popup_mode = 'filter'
            
        self.popup = Popup(title='フィルタ', content=content, size_hint=(None, None), size=(800, 600), auto_dismiss=True)
        self.popup.open()

    def adapt_filter(self, tp, eo_active):

        sm = self.root.ids.sm

        if sm.current is 'InitialScreen':
            print('OR enable : ', eo_active)
            for th in tp.tab_list:
                #print('[{0}] - [{1}]'.format(acc_item.title, acc_item.id))
                print('[{0}]'.format(th.text))
                for fi in th.content.ids.fi.children:
                    print('{0} - {1}'.format(fi.text, fi.ids.cb.active))

        elif sm.current is 'DataBaseItemsView':
            self.db_filter['options']={}
            for th in tp.tab_list:
                key = th.text
                for fi in th.content.ids.fi.children:
                    if fi.ids.cb.active:
                        if key in self.db_filter['options'].keys():
                            self.db_filter['options'][key].append(fi.text)
                        else:
                            self.db_filter['options'][key] = [fi.text]
            self.db_filter['enable_or'] = eo_active

            self.reload_db_header(filt_on=True)
            self.reload_db_items()

        elif sm.current is 'ThumbnailView':
            filter_option={}
            for th in tp.tab_list:
                for fi in th.content.ids.fi.children:
                    # TODO:GUIの日本語表示と内部の表現の切り替えの仕方を検討する
                    if fi.text == 'お気に入り':
                        filter_option['favorite'] = fi.ids.cb.active
                    elif fi.text == 'チャプター':
                        filter_option['chapter'] = fi.ids.cb.active

            self.reload_thumbnailview(filter_option=filter_option, enable_or=eo_active)

        self.close_popup()

    def exit_filter(self,instance):
        self.db_filter['options'] = {}
        self.db_filter['enable_or'] = False
        self.reload_db_header()
        self.reload_db_items()

    def _on_drop_files(self, window, file_path):

        path = file_path.decode('utf-8')
        
        # ドロップしたスクリーン別に操作を変える
        sm = self.root.ids.sm
        if sm.current is 'DataBaseItemsView':
            if self.popup_mode == 'close':
                self.open_entry_popup()

            if self.popup_mode == 'data_entry':
                if os.path.isdir(path):
                    self.entry_count += 1            
                    self.add_new_entry(path)
            
            elif self.popup_mode == 'tag_setting':
                _, ext = os.path.splitext(path)
                if ext in [".jpg", ".jpeg", ".png", ".bmp"]:
                    self.popup.content.im_source = path
        
        if sm.current is 'ThumbnailView':
            if self.popup_mode == 'close':
                self.open_file_entry_popup()

            if self.popup_mode == 'file_entry':
                if os.path.isdir(path):
                    file_list = sorted(list(chain.from_iterable([glob.glob(os.path.join(path, "*." + ext)) for ext in self.dbm.SUPPORTED_EXT])))
                    for fl in file_list:
                        self.add_file_entry(fl)
                elif os.path.isfile(path):
                    _, ext = os.path.splitext(path)
                    if ext in ['.'+e for e in self.dbm.SUPPORTED_EXT]:
                        self.add_file_entry(path)

        return


    # DataBaseItemsViewイベント
    def go_databaseitemsview(self, db_root=None):
        
        # インスタンス取得
        self.dbm = databasemanager.DataBaseManager() 

        # データベース作成
        # TODO; テスト用 - 実際には前画面から取得する
        db_root = os.path.join(self.curdir,'data', '__tmp__', 'testDB')

        self.db_root = db_root
        if not self.dbm.connect_database(self.db_root):
            # TODO: 実際には、データベース作成画面がPopupされる予定
            additional_tags = {
                'タイプ': 'text',
                'ジャンル': 'text',
                'Misc': 'text'
            }
            self.dbm.create_database(self.db_root,additional_tags=additional_tags)

        # 各タグの最大登録数はjsonファイルに記録しておく
        tag_file = open(os.path.join(self.db_root, 'tags.json'), 'r')
        self.db_tags  = json.load(tag_file)
        self.logger.debug('read {} -> {}'.format(tag_file, self.db_tags))

        self.reload_db_header()
        self.reload_db_items()
        
        sm = self.root.ids.sm
        sm.transition = SlideTransition(direction='left', duration=self.animation_speed)
        sm.current = 'DataBaseItemsView'
        self.screen_title = 'データベース内容'

    def adapt_ic_filter(self, instance):
        if instance.state == 'normal':
            self.db_filter['init_chars'] = []
        else:
            ic = instance.text
            self.db_filter['init_chars'] = copy.deepcopy(self.ic_filter_map[ic])
        self.reload_db_items()

    def switch_db_view(self, spinner, text):
        self.db_view_mode = text
        self.reload_db_items()
    
    def chage_db_mode_favorite(self, instance):
        self.db_filter['is_favorite'] ^= True
        tmp_txt = 'フィルタOFF' if self.db_filter['is_favorite'] else 'フィルタON'
        instance.text = tmp_txt
        self.reload_db_items()

    def select_db_item(self, instance):

        if self.db_view_mode == 'Title':
            if self.item_select_mode is 'normal':
                self.data_title = instance.title
                self.go_thumbnailview()

            elif self.item_select_mode is 'trash':
                instance.is_selected ^= True

            elif self.item_select_mode is 'favorite':
                instance.is_favorite ^= True
                self.dbm.update_record(title=instance.title, values_dict={'IsFavorite':int(instance.is_favorite)})

            elif self.item_select_mode is 'tag':
                self.open_tag_edit(instance.title)

            elif self.item_select_mode is 'link':
                url = self.dbm.get_items('Link', title=instance.title, convert=True)
                if not url[0] is None:
                    if not url[0] == '':
                        webbrowser.open(url[0])
        else:
            if self.item_select_mode is 'normal':
                self.db_filter['options'] = {self.db_view_mode:[instance.title]}
                self.db_filter['enable_or'] = False
                self.reload_db_header(filt_on=True)
                self.reload_db_items()
            elif self.item_select_mode is 'favorite':
                instance.is_favorite ^= True
                self.dbm.update_tag(self.db_view_mode, instance.title, values_dict={'IsFavorite':int(instance.is_favorite)})

            elif self.item_select_mode is 'link':
                url = self.dbm.get_tag_items(self.db_view_mode, 'Link', instance.title, convert=True)
                if not url[0] is None:
                    if not url[0] == '':
                        webbrowser.open(url[0])

    def reload_db_header(self, filt_on=False):
        # ビューの設定
        sm = self.root.ids.sm
        screen = sm.get_screen('DataBaseItemsView')

        # ヘッダー部分のレイアウト作成
        screen.ids.header.clear_widgets()
        
        if filt_on:
            self.db_view_mode = 'Title'

            filt_info = BoxLayout(orientation='vertical', spacing=2)
            filt_info.add_widget(Label(text='フィルタ適用中', font_size=20))
            filt_txt = []
            for key, val in sorted(self.db_filter['options'].items(), key=lambda x:x[0]):
                filt_txt.append('{}({})'.format(key, ','.join(val)))
            sub_txt = 'OR: ' if self.db_filter['enable_or'] else 'AND: '
            filt_info.add_widget(Label(text= sub_txt + ','.join(filt_txt), font_size=14))

            a_layout_r = AnchorLayout(anchor_x='right', anchor_y='center')
            a_layout_r.add_widget(Button(text='解除', size_hint=(None,None), size=(100, 40), on_release=self.exit_filter))
            
            screen.ids.header.add_widget(filt_info)
            screen.ids.header.add_widget(a_layout_r)

        else:
            a_layout_l = AnchorLayout(anchor_x='left', anchor_y='center')

            b_layout = BoxLayout(spacing=5)
            b_layout.add_widget(Label(size_hint_x=None, width=100, text='表示切替', font_size=20))
            tmp_list = ['Title'] + list(sorted(self.db_tags.keys()))
            sp = Spinner(size_hint_x=None, width=150, values=tmp_list, text='Title')
            sp.bind(text=self.switch_db_view)
            b_layout.add_widget(sp)

            a_layout_l.add_widget(b_layout)
            screen.ids.header.add_widget(a_layout_l)

    def reload_db_items(self):

        self.logger.debug('reload db items')

        # ビューの設定
        sm = self.root.ids.sm
        screen = sm.get_screen('DataBaseItemsView')

        # 現在の要素を削除
        screen.ids.dbitems.clear_widgets()

        if self.db_view_mode == 'Title':
            # タイトルとファイル数の一覧を取得する
            #tmp_info = self.dbm.get_items(['Title','FileNum','IsFavorite'], convert=False)
            tmp_info = self.dbm.get_titles(filter_option=self.db_filter['options'], init_chars=self.db_filter['init_chars'], enable_or=self.db_filter['enable_or'])
            for ti in tmp_info:

                if ti[2] is None:
                    is_fav = False
                else:
                    is_fav = bool(ti[2])

                if self.db_filter['is_favorite'] & (not is_fav):
                    continue

                dbitem = DBItem(title=ti[0], filenum=ti[1], is_favorite=is_fav)
                screen.ids.dbitems.add_widget(dbitem)
        else:
            tmp_info = self.dbm.get_tag_items_with_num(self.db_view_mode, init_chars=self.db_filter['init_chars'])
            for tname, vals in sorted(tmp_info.items(), key=lambda x:x[0]):
                if vals[1] is None:
                    is_fav = False
                else:
                    is_fav = bool(vals[1])

                if self.db_filter['is_favorite'] & (not is_fav):
                    continue

                dbitem = DBItem(title=tname, filenum=vals[0], is_favorite=is_fav)
                screen.ids.dbitems.add_widget(dbitem)

    def delete_db_items(self, instance):
        
        # ビューの設定
        sm = self.root.ids.sm
        screen = sm.get_screen('DataBaseItemsView')

        # 削除対象の一覧を取得
        self.del_title = []
        for dbitem in screen.ids.dbitems.children:
            if dbitem.is_selected:
                self.del_title.append(dbitem.title)

        if len(self.del_title) == 0:
            return

        # 確認画面
        msg = '削除します。よろしいですか？'
        msg_lines = ['-----Titles-----'] + self.del_title
        content = YesNoPopUp(text=msg, subtext='\n'.join(msg_lines), yes=self.start_delete, no=self.close_confirm_popup)
        self.c_popup = Popup(title="確認", content=content, size_hint=(None, None), size=(400, 400), auto_dismiss=False)
        self.c_popup.open()
        
        return
        
    def start_delete(self):

        self.op_is_active = True
        self.close_confirm_popup()

        # 削除
        self.dbm.delete_record(self.del_title)

        self._open_progress('delete')


    # タグ操作
    def open_tag_setting(self, instance):

        sm = self.root.ids.sm

        if not sm.current is 'DataBaseItemsView':
            return

        #ポップアップ構造のテンプレート読み込み
        content = self._load_template('TagPopUp')
        tp = content.ids.tp
        tp.clear_tabs()

        # 登録済みのタグ一覧を取得する
        tag_list = {}
        for key in sorted(self.db_tags.keys()):
            tag_list[key] = self.dbm.get_tag_items(key, 'Name', convert=True)
        #print(tag_list)

        for key, val_list in sorted(tag_list.items(), key=lambda x:x[0]):
            #tp_item = TabbedPanelItem(text=key)
            th = TabbedPanelHeader(text=key)
            filter_items = self._load_template('FilterItems')
            for val in val_list:
                #print('{0} - {1}'.format(key, val))
                #filter_items.ids.fi.add_widget(FilterItem(text=val))
                filter_items.ids.fi.add_widget(TagEditItem(text=val))
            
            th.content = filter_items
            tp.add_widget(th)
            
        self.popup = Popup(title='タグ編集', content=content, size_hint=(None, None), size=(900, 760), auto_dismiss=False)
        self.popup.open()

        self.popup_mode = 'tag_setting'
    
    def reflect_tag(self, tag_item, is_active):

        content = self.popup.content
        if is_active:
            table = content.ids.tp.current_tab.text
            tag_name = tag_item.text

            content.ids.tag_input.text = tag_name

            res = self.dbm.get_tag_items(table, ['InitialCharacter','Link'], name=tag_name, convert=False)
            content.ids.ic_btn.text = res[0][0]
            content.ids.link_input.text = res[0][1] if not res[0][1] is None else ''

            im_path = self.dbm.get_tag_image(table, tag_name)
            if im_path == '':
                content.im_source = self.NO_IMAGE
            else:
                content.im_source = im_path
        else:
            self._clear_tag_info()

    def add_tag(self, tp, input_tag, ic_btn, link_input):
        
        table = tp.current_tab.text
        tn = input_tag.text
        ic = ic_btn.text
        li = link_input.text

        if table=='Default tab':
            return

        if (tn == '') | (ic == '') :
            return

        if self.popup.content.im_source == self.NO_IMAGE:
            tim = ''
        else:
            tim = self.popup.content.im_source

        if self.dbm.add_tag(table, (tn,ic, li,tim)):
            #tp.current_tab.content.ids.fi.add_widget(FilterItem(text=tag_name))
            tp.current_tab.content.ids.fi.add_widget(TagEditItem(text=tn))
            self._clear_tag_info()
        else:
            c_content = SimplePopUp(text='同名のタグがあります', close=self.close_confirm_popup)
            self.c_popup = Popup(title="警告", content=c_content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
            self.c_popup.open()

    def add_tag_on_entry(self, table, tag_name, initial_char):

        if (table == '') | (tag_name == '') | (initial_char == '') :
            return

        if self.dbm.add_tag(table, (tag_name,initial_char, '', '')):
            tag_list = sorted([''] + self.dbm.get_tag_items(table, 'Name', convert=True))
            for th in self.popup.content.ids.tp.tab_list:
                for child in th.content.children:
                    if child.__class__.__name__ is 'TagEditLayout':
                        key = child.title
                        if key == table:
                            for ch in child.children:
                                if ch.__class__.__name__ is 'GridLayout':
                                    for c in ch.children:
                                        c.values = tag_list
        else:
            c_content = SimplePopUp(text='同名のタグがあります', close=self.close_confirm_popup)
            self.c_popup = Popup(title="警告", content=c_content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
            self.c_popup.open()

    def change_tag(self, tp):

        content = self.popup.content
        
        table = content.ids.tp.current_tab.text
        new_name = content.ids.tag_input.text
        ic_text = content.ids.ic_btn.text
        link_str = content.ids.link_input.text
        
        # 選択中の要素を取得する
        select_child = None
        old_name = ''
        tag_layout = tp.current_tab.content.ids.fi
        for child in tag_layout.children:
            if child.ids.cb.active:
                select_child = child
                old_name = child.text
                break
        if old_name == '': # なければ空欄のままなのでreturn
            return

        values_dict = {}
        values_dict['InitialCharacter'] = ic_text
        values_dict['Link'] = link_str

        old_im_path = self.dbm.get_tag_image(table, old_name)
        if old_im_path == '':
            old_im_path = self.NO_IMAGE

        if self.popup.content.im_source != old_im_path:
            new_im_path = '' if self.popup.content.im_source==self.NO_IMAGE else self.popup.content.im_source
            values_dict['Image'] = new_im_path

        if old_name != new_name:
            values_dict['Name'] = new_name
            self.popup.content.im_source = self.NO_IMAGE

        self._clear_tag_info()

        if self.dbm.update_tag(table, old_name, values_dict):
            select_child.text = new_name
        else:
            c_content = SimplePopUp(text='同名のタグがあります', close=self.close_confirm_popup)
            self.c_popup = Popup(title="警告", content=c_content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
            self.c_popup.open()

        return

    def delete_tag(self, tp):

        self._clear_tag_info()

        tag_layout = tp.current_tab.content.ids.fi

        del_child = None
        del_name = ''
        for child in tag_layout.children:
            if child.ids.cb.active:
                del_child = child
                del_name = child.text
                break
        if del_name == '':
            return

        self.dbm.delete_tags(tp.current_tab.text, [del_name])

        tag_layout.remove_widget(del_child)

        return

    def exclude_tag_image(self):
        self.popup.content.im_source = self.NO_IMAGE

    def _clear_tag_info(self):
        content = self.popup.content
        content.ids.tag_input.text = ''
        content.ids.ic_btn.text = ''
        content.ids.link_input.text = ''
        content.im_source = self.NO_IMAGE


    def open_tag_edit(self, title):

        content = self._load_template('TagEdit')
        content.sp_values = sorted(list(self.db_tags.keys()))

        # テンプレート情報の読み取り
        col_name = ['Title', 'InitialCharacter', 'Updated', 'FileNum', 'Size', 'Link']
        tmp_info = self.dbm.get_items(col_name=col_name, title=title, convert=False)
        #for ti in tmp_info[0]:
            #print(type(ti), ti)

        content.ids.title_input.text = tmp_info[0][0]
        content.ids.ic_btn.text = tmp_info[0][1]
        content.ids.link_input.text = tmp_info[0][5]

        content.before_title = tmp_info[0][0]
        content.updated = tmp_info[0][2].strftime('%Y-%m-%d %H:%M:%S')
        content.filenum = str(tmp_info[0][3])
        content.datasize = '{:.2f}'.format(tmp_info[0][4])

        # 登録済みのタグ一覧を取得する
        tag_list = {}
        for key in sorted(self.db_tags.keys()):
            tag_list[key] = self.dbm.get_tag_items(key, 'Name', convert=True)
        #print(tag_list)
 
        for key, value in sorted(tag_list.items(), key=lambda x:x[0]):

            data_tags = self.dbm.get_items(col_name=key, title=title, convert=True)
            #print(data_tags)

            ni = TagEditLayout(title=key)
            g_layout =GridLayout(cols=3)
            tmp_value = [''] + value
            for i in range(self.db_tags[key]):
                
                if i < len(data_tags):
                    sp_text = str(data_tags[i])
                else:
                    sp_text = ''
                sp = Spinner(text=sp_text, values=tmp_value, size_hint=(None, None), size=(200, 30))
                g_layout.add_widget(sp)
            ni.add_widget(g_layout)
            content.ids.te_layout.add_widget(ni)

        self.popup = Popup(title='データ情報', content=content, size_hint=(None, None), size=(900, 760), auto_dismiss=False)
        self.popup.open()

    def change_entry_info(self, instance):

        values_dict = {}

        before_title = instance.before_title
        new_title = instance.ids.title_input.text
        if not before_title == new_title:
            msg = ''
            if new_title is '':
                msg = 'タイトルが未入力です'
            elif self.dbm.title_is_exist(title=new_title):
                msg = '登録済みのタイトル名です'
            if not msg is '':
                content = SimplePopUp(text=msg, close=self.close_confirm_popup)
                self.c_popup = Popup(title="警告", content=content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
                self.c_popup.open()
                return
            else:
                values_dict['Title'] = new_title

        values_dict['InitialCharacter'] = instance.ids.ic_btn.text
        values_dict['Link'] = instance.ids.link_input.text

        #TODO: 「クラス名で必要な情報を取得する」というゴリ押しを何とかしたい。
        for child in instance.ids.te_layout.children:
            if child.__class__.__name__ is 'TagEditLayout':
                key = child.title
                tmp_list = set([])
                for ch in child.children:
                    if ch.__class__.__name__ is 'GridLayout':
                        for c in ch.children:
                            if not c.text is '':
                                tmp_list.add(c.text)
                values_dict[key] = list(copy.deepcopy(tmp_list))

        self.dbm.update_record(title=before_title, values_dict=values_dict)

        content = SimplePopUp(text='変更しました！', close=self.close_confirm_popup)
        self.c_popup = Popup(title="情報変更", content=content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
        self.c_popup.open()

        self.reload_db_items()

        return


    # データ登録ポップアップでのイベント
    def open_entry_popup(self):
        self.popup_mode = 'data_entry'

        content = self._load_template('DataEntry')
        content.sp_values = sorted(list(self.db_tags.keys()))
        self.popup = Popup(title='データ登録', content=content, size_hint=(None, None), size=(900, 760), auto_dismiss=False)
        self.popup.open()
        self.op_is_active = True

    def close_entry_popup(self):
        self.close_popup()
        self.op_is_active = False
        self.entry_count = 0
        self.error_entry = []

    def add_new_entry(self, path):

        tp = self.popup.content.ids.tp

        # 登録済みのタグ一覧を取得する
        tag_list = {}
        for key in sorted(self.db_tags.keys()):
            tag_list[key] = self.dbm.get_tag_items(key, 'Name', convert=True)
        #print(tag_list)

        th = TabbedPanelHeader(text='{}'.format(self.entry_count))
        ne_layout = NewEntryLayout()
        ne_layout.ids.path_input.text = path
        ne_layout.ids.title_input.text = os.path.basename(path)
        for key, value in sorted(tag_list.items(), key=lambda x:x[0]):
            ni = TagEditLayout(title=key)
            g_layout =GridLayout(cols=3)
            tmp_value = sorted([''] + value)
            for i in range(self.db_tags[key]):
                sp = Spinner(values=tmp_value, size_hint=(None, None), size=(200, 30), font_size=14)
                g_layout.add_widget(sp)
            ni.add_widget(g_layout)
            ne_layout.add_widget(ni)
        th.content = ne_layout
        tp.add_widget(th)

    def delete_entry(self, tp):
        cur_tab = tp.current_tab

        # currentタブが存在する必要がある。
        is_exist = False
        for th in tp.tab_list:
            if th.text == cur_tab.text:
                is_exist = True
                break

        if is_exist:
            cur_tab.content.clear_widgets()
            tp.remove_widget(cur_tab)

    def data_entry(self, tp, enable_move):
        
        self.file_move = enable_move
        self.reserved_entry = []
        except_msg = []

        for th in tp.tab_list:

            values_dict = {}
            
            path = th.content.ids.path_input.text
            title = th.content.ids.title_input.text
            ichar = th.content.ids.ic_btn.text
            link_str = th.content.ids.link_input.text

            if (path is '') | (title is '') | (ichar is ''):
                except_msg.append('{} : 未入力の必須項目があります'.format(th.text))
                continue

            if self.dbm.title_is_exist(title):
                except_msg.append('{} : 同名タイトルが登録済みです'.format(th.text))
                continue
            
            values_dict['InitialCharacter'] = ichar
            values_dict['Link'] = link_str

            #TODO: 「クラス名で必要な情報を取得する」というゴリ押しを何とかしたい。
            for child in th.content.children:
                if child.__class__.__name__ is 'TagEditLayout':
                    key = child.title
                    tmp_list = set([])
                    for ch in child.children:
                        if ch.__class__.__name__ is 'GridLayout':
                            for c in ch.children:
                                if not c.text is '':
                                    tmp_list.add(c.text)
                    values_dict[key] = list(copy.deepcopy(tmp_list))

            self.reserved_entry.append({
                'path':path,
                'Title':title,
                'values_dict':copy.deepcopy(values_dict)
            })

        if len(except_msg) != 0:
            content = SimplePopUp(text='\n'.join(except_msg), close=self.close_confirm_popup)
            self.c_popup = Popup(title="警告", content=content, size_hint=(None, None), size=(400, 300), auto_dismiss=True)
        else:
            msg = '次の内容で登録します。よろしいですか？'
            msg_lines = []
            for re in self.reserved_entry:
                msg_lines.append('--- {} ---'.format(re['Title']))
                for k,v in re['values_dict'].items():
                    if type(v) is list:
                        sub_msg = ','.join([str(r) for r in v])
                    else:
                        sub_msg = str(v)
                    msg_lines.append('\t{}: {}'.format(k, sub_msg))
            content = YesNoPopUp(text=msg, subtext='\n'.join(msg_lines), yes=self.start_entry, no=self.cancel_entry)
            self.c_popup = Popup(title="確認", content=content, size_hint=(None, None), size=(600, 500), auto_dismiss=False)
        self.c_popup.open()

    def start_entry(self):
        
        self.close_confirm_popup()

        self.error_entry = []
        self.error_entry = self.dbm.insert_records(self.reserved_entry)

        if len(self.error_entry) != len(self.reserved_entry):
            self.dbm.start_copy()
            self._open_progress('copy')

        return

    def cancel_entry(self):
        self.reserved_entry = []
        self.close_confirm_popup()
        return


    def _open_progress(self, p_type):
        if p_type == 'copy':
            content = ProgressPopUp()
            self.p_popup = Popup(title="コピー進捗", content=content, size_hint=(None, None), size=(600, 200), auto_dismiss=False)
        elif p_type == 'delete':
            content = Label(text='しばらくお待ちください。', font_size=16)
            self.p_popup = Popup(title="データ削除中", content=content, size_hint=(None, None), size=(300, 150), auto_dismiss=False)

        self.p_popup.open()
        Clock.schedule_interval(partial(self._file_op_progress, p_type), 0.1)

    def _file_op_progress(self, mode, *largs):

        if mode is 'copy':
            # 進捗の確認
            cp_progress = self.dbm.get_copy_progress()
            # GUI側への反映
            self.now_title = cp_progress['title']
            self.now_task = cp_progress['task_index']
            self.task_num = cp_progress['task_num']
            self.task_copied_file = cp_progress['copied_file']
            self.task_file_num = cp_progress['file_num']
            self.task_progress = (self.task_copied_file/self.task_file_num) * 100

        # コピー進捗の確認
        if self.dbm.file_op_is_alive():
            return True
        else:
            # 完了後の処理を行う。内部のactiveフラグで一度のみ実行されるようにしている
            if not self.op_is_active:
                return False
                
            self.p_popup.dismiss()
            msg_lines = ['処理が完了しました！']

            if mode is 'copy':
                if len(self.error_entry) != 0:
                    msg_lines.append('[登録失敗]')
                    msg_lines += self.error_entry
                self.close_entry_popup()
                    
            elif mode is 'delete': 
                self.op_is_active = False

            # TODO: スレッド外でSQL文が実行できないため、
            # フラグを立ててpopupのクローズイベントと同時に行っているが、無理やり感がある
            self.task_remain = True

            content = SimplePopUp(text='\n'.join(msg_lines), close=self.close_confirm_popup)
            self.c_popup = Popup(title="登録完了", content=content, size_hint=(None, None), size=(400, 300), auto_dismiss=False)
            self.c_popup.open()
            
            return False


    # ThumbnailViewイベント
    def go_thumbnailview(self):
        
        self.reload_data()
        
        """
        # テスト用
        for opt_key in self.image_option.keys():
            for i in range(self.image_num):
                if opt_key is 'favorite':
                    self.image_option[opt_key][i] = ((i % 10) == 0)
                elif opt_key is 'chapter':
                    self.image_option[opt_key][i] = ((i % 23) == 0)
        """

        self.screen_title = 'サムネイルビュー'
        sm = self.root.ids.sm
        sm.transition = SlideTransition(direction='left', duration=self.animation_speed)
        sm.current = 'ThumbnailView'

        self.reload_thumbnailview()

    def reload_data(self):

        self.image_dir, self.image_list = self.dbm.get_image_list(self.data_title)
        self.image_num = len(self.image_list)

        self.logger.debug('get {} images from {}'.format(self.image_num, self.data_title))

        # TODO : エラーハンドリング
        if self.image_num == 0:
            pass
        
        self.image_selected = np.zeros(self.image_num, dtype=bool)
        
        for opt_key in self.image_option.keys():
            self.image_option[opt_key] = np.zeros(self.image_num, dtype=bool)

        # オプション値の読み取り
        for opt_key in self.image_option.keys():
            result = self.dbm.get_items(col_name=opt_key, title=self.data_title, convert=True)
            self.logger.debug('get option {} -> {}'.format(opt_key, result))
            
            opt_val = result[0]
            if opt_val is None:
                break
            elif type(opt_val) is str:
                if not opt_val is '':
                    self.image_option[opt_key][int(opt_val)] = True
            elif type(opt_val) is list:
                for ov in opt_val:
                    self.image_option[opt_key][int(ov)] = True

        
    def reload_thumbnailview(self, filter_option=None, enable_or=False):

        self.image_view_index = []

        if filter_option is None:
            self.image_view_index = [i for i in range(self.image_num)]

        else:
            tmp_list = np.zeros(self.image_num, dtype=bool)
            tmp_list[:] = (not enable_or)

            for opt, flag in filter_option.items():

                if flag:
                    opt_list = self.image_option[opt][:]
                    if enable_or:
                        tmp_list |= opt_list
                    else:
                        tmp_list &= opt_list

            for i in range(self.image_num):
                if tmp_list[i]:
                    self.image_view_index.append(i)

        self.image_view_num = len(self.image_view_index)

        # TODO:エラーハンドリング - ポップアップ表示して、option is Noneにする
        if self.image_view_num == 0:
            filter_option = None
            self.image_view_index = [i for i in range(self.image_num)]
            self.image_view_num = len(self.image_view_index)

        self.divided_index = 0
        self.divided_num = math.ceil(self.image_view_num / self.max_thumnail)

        self.image_filter_mode = filter_option

        self.change_thumbnailview('1')

    def change_thumbnailview(self, jump_info):

        current_idx = self.divided_index

        if type(jump_info) is str:
            jump_text = jump_info
        else:
            jump_text = jump_info.text
        
        if jump_text.isdecimal():
            next_index = int(jump_text)
            if (next_index < 1) | (self.divided_num < next_index):
                return
        else:
            # 一つ前へ
            if jump_text == '<':
                if current_idx != 1:
                    next_index = self.divided_index - 1
                else:
                    return
            # 一つ後へ
            elif jump_text == '>':
                if current_idx != self.divided_num:
                    next_index = self.divided_index + 1
                else:
                    return
            # ジャンプ
            elif jump_text == '...':
                self.open_jump_popup()
                return
            else:
                return
    
        if current_idx == next_index:
            return

        self._wait_cancel()

        self.divided_index = next_index

        st_idx = (self.divided_index-1) * self.max_thumnail
        ed_idx = st_idx + self.max_thumnail-1
        if ed_idx >= self.image_view_num:
            ed_idx = self.image_view_num-1
        self.divided_slice[0] = st_idx
        self.divided_slice[1] = ed_idx
        self.thumbnail_num = ed_idx - st_idx + 1 

        #self._update_jump_buttons()
        self._reload_jump_layout()

        # 既存サムネイルの削除
        self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails.clear_widgets()

        self.threads['load_thumbnails'] = threading.Thread(target=self._add_thumbnails, daemon=True)
        self.threads['load_thumbnails'].start()

    def open_jump_popup(self):

        self.popup_mode = 'jump'
        
        content = JumpPopUp()
        self.popup = Popup(title='ページ移動', content=content, size_hint=(None, None), size=(300, 150), auto_dismiss=True)
        self.popup.open()

    def jump_thumbnail(self, text):
        self.change_thumbnailview(text)
        self.close_popup()

    def _reload_jump_layout(self):

        layout = self.root.ids.sm.get_screen('ThumbnailView').ids.jump_layout
        layout.clear_widgets()

        layout.add_widget(ThumbnailJump(text='<'))
        if self.max_jump_button >= self.divided_num:
            for i in range(self.divided_num):
                layout.add_widget(ThumbnailJump(text='{}'.format(i+1)))
        else:
            change_num = self.max_jump_button - 2
            if self.divided_index < change_num:
                for i in range(change_num):
                    layout.add_widget(ThumbnailJump(text='{}'.format(i+1)))
                layout.add_widget(ThumbnailJump(text='...'))
                layout.add_widget(ThumbnailJump(text='{}'.format(self.divided_num)))
            elif self.divided_index > (self.divided_num - change_num + 1):
                layout.add_widget(ThumbnailJump(text='{}'.format(1)))
                layout.add_widget(ThumbnailJump(text='...'))
                for i in range(self.divided_num-change_num+1,self.divided_num+1):
                    layout.add_widget(ThumbnailJump(text='{}'.format(i)))
            else:
                change_num -= 2
                layout.add_widget(ThumbnailJump(text='{}'.format(1)))
                layout.add_widget(ThumbnailJump(text='...'))
                for i, diff in enumerate(range(int(-change_num/2), math.ceil(change_num/2))):
                    jump_index = self.divided_index + diff
                    layout.add_widget(ThumbnailJump(text='{}'.format(jump_index)))
                layout.add_widget(ThumbnailJump(text='...'))
                layout.add_widget(ThumbnailJump(text='{}'.format(self.divided_num)))
        layout.add_widget(ThumbnailJump(text='>'))
        layout.width = 48 * len(layout.children)

        for jump_btn in layout.children:
            if jump_btn.text.isdecimal():
                if self.divided_index == int(jump_btn.text):
                    jump_btn.background_color = [0.0, 0.5, 0.8, 1.0]
                else:
                    jump_btn.background_color = [0.6, 0.6, 0.6, 0.8]
            else:
                jump_btn.background_color = [0.6, 0.6, 0.6, 0.8]

    def _add_thumbnails(self):

        # スクリーン移動のアニメーション用のスリープ
        if self.loading_screen:
            time.sleep(self.animation_speed + 0.1)
            self.loading_screen = False
        
        self.loading_thumbnail = False
        screen = self.root.ids.sm.get_screen('ThumbnailView')

        for i, idx in enumerate(range(self.divided_slice[0], self.divided_slice[1]+1)):

            if self.load_cancel:
                return

            while(self.loading_thumbnail):
                pass
            
            thumbnail = self._load_template('Thumbnail')
            thumbnail.im_index = self.image_view_index[idx]

            screen.ids.thumbnails.add_widget(thumbnail)
            
            self.loading_thumbnail = True
            Clock.schedule_once(self._update_thumbnail)

            self.progress = ((i+1) / self.thumbnail_num) * 100

        return

    def _update_thumbnail(self, dt):
        
        try:
            thumbnail = self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails.children[0]

            im_index = thumbnail.im_index
            
            file_base, ext = os.path.splitext(self.image_list[im_index])
            if ext == '.zip':
                thum_name = os.path.basename(file_base) + '.png'
                thum_path = os.path.join(self.image_dir, '__thumbnail__', thum_name)
                #print(thum_path)
                thumbnail.im_source = thum_path
            else:
                thumbnail.im_source = os.path.join(self.image_dir, self.image_list[im_index])
            
            thumbnail.fa_source = 'data/icons/star.png'
            thumbnail.ch_source = 'data/icons/bookmark.png'

            thumbnail.is_selected = self.image_selected[im_index]

            # TODO: 増えてくるようならここもfor文で回せないかを検討する
            thumbnail.is_favorite = self.image_option['favorite'][im_index]
            thumbnail.is_chapter = self.image_option['chapter'][im_index]
            
        finally:
            self.loading_thumbnail = False
            return

    def _save_image_option(self):
        """
        設定したオプションのデータベースへの反映。
        """

        save_dict = {}
        for opt_key, opt_val in self.image_option.items():
            index = np.where(opt_val)
            index_list = list(index[0])
            
            save_dict[opt_key] = copy.deepcopy(index_list)
            self.logger.debug('update {}'.format(save_dict))

        self.dbm.update_record(self.data_title, save_dict)

    # ファイルの追加
    def open_file_entry_popup(self):
        self.popup_mode = 'file_entry'
        self.entry_files = []

        msg = '次の画像を追加します。よろしいですか？'
        content = YesNoPopUp(text=msg, subtext='', yes=self.start_file_entry, no=self.close_popup)
        self.popup = Popup(title="確認", content=content, size_hint=(None, None), size=(600, 500), auto_dismiss=False)
        self.popup.open()
        self.op_is_active = True

    def add_file_entry(self, path):
        self.entry_files.append(path)
        self.popup.content.subtext += (os.path.basename(path) + '\n')

    def start_file_entry(self):

        if len(self.entry_files) == 0:
            return

        self.error_entry = []
        self.dbm.add_files(self.data_title, self.entry_files)
        
        self.dbm.start_copy()
        self._open_progress('copy')

    # 画像選択モード
    def select_image(self, thumbnail):

        if self.root.ids.sm.current != 'ThumbnailView':
            return

        im_index = thumbnail.im_index

        # イメージビューへ 
        if self.item_select_mode is 'normal':

            self._wait_cancel()

            self.image_file_path = os.path.join(self.image_dir, self.image_list[im_index])
            self.image_file_name = self.image_list[im_index]
            self.image_idx = im_index

            #self._reset_mode() #normalモード以外では移らないのでいらない
            
            self.screen_title = 'イメージビューワー'
            sm = self.root.ids.sm
            sm.transition = RiseInTransition()
            sm.current = 'ImageView'
        
        # 画像選択モード
        else:

            # 範囲選択がONの場合
            if self.range_selectable:

                # 基準位置が未選択
                if self.range_select_base is None:
                    
                    thumbnail.is_based = True
                    self.range_select_base = im_index
                
                # 基準位置が選択済み
                else:

                    if self.range_select_base < im_index:
                        s_index = self.range_select_base
                        e_index = im_index
                    else:
                        s_index = im_index
                        e_index = self.range_select_base
                    
                    if self.item_select_mode is 'trash':
                        self.image_selected[s_index:e_index+1] = True
                    else:
                        self.image_option[self.item_select_mode][s_index:e_index+1] ^= True
                        self._save_image_option()
                    
                    self.range_select_base = None
                    self._update_all_thumbnail_color()

            # 単一選択
            else:
                if self.item_select_mode is 'trash':
                    self.image_selected[im_index] ^= True
                    thumbnail.is_selected ^= True 
                else:
                    self.image_option[self.item_select_mode][im_index] ^= True
                    self._save_image_option()
                    if self.item_select_mode is 'favorite':
                        thumbnail.is_favorite ^= True
                    elif self.item_select_mode is 'chapter':
                        thumbnail.is_chapter ^= True

        return

    def change_range_option(self, instance):
        self.range_selectable ^= True

    def delete_images(self, instance):
        #TODO: 選択画像の削除 - データベースの方針決定が先のため保留
        print('delete clicked')
        pass
    
    def _update_all_thumbnail_color(self):
        
        for child in self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails.children:

            im_index = child.im_index

            child.is_based = False
            child.is_selected = self.image_selected[im_index]

            child.is_favorite = self.image_option['favorite'][im_index]
            child.is_chapter = self.image_option['chapter'][im_index] 


    # ImageViewerイベント
    def change_view_image(self, option='next'):
        
        tmp_index = None

        if option is 'next':
            if self.item_select_mode in ['normal', 'trash']:
                tmp_index = self.image_idx + 1
            elif self.item_select_mode in ['favorite','chapter']:
                for i in range(self.image_idx+1, self.image_num):
                    if self.image_option[self.item_select_mode][i]:
                        tmp_index = i
                        break

        elif option is 'previous':
            if self.item_select_mode in ['normal', 'trash']:
                tmp_index = self.image_idx - 1
            elif self.item_select_mode in ['favorite','chapter']:
                for i in reversed(range(0, self.image_idx)):
                    if self.image_option[self.item_select_mode][i]:
                        tmp_index = i
                        break

        if tmp_index is None:
            return
        elif (tmp_index < 0) | (self.image_num-1 < tmp_index):
            return
        else:
            self.image_idx = tmp_index
            self.image_file_path = os.path.join(self.image_dir, self.image_list[tmp_index])
            self.image_file_name = self.image_list[tmp_index]
            self.root.ids.sm.get_screen('ImageView').anim_speed = 0.05


        return

    def change_view_fullscreen(self):
        self.hide_menu ^= True

        ab = self.root.ids.ab
        iv_footer = self.root.ids.sm.get_screen('ImageView').ids.iv_footer

        if self.hide_menu:
            ab_height = 0
            iv_footer_height = 0
        else:
            ab_height = 40
            iv_footer_height = 70

        Animation(height=ab_height, d=.3, t='out_quart').start(ab)
        Animation(height=iv_footer_height, d=.3, t='out_quart').start(iv_footer)

    def change_anim_speed(self, instance, option):

        if option == 'up':
            tmp_speed = instance.anim_speed*0.5
            instance.anim_speed = tmp_speed if (tmp_speed > 0.025) else 0.025
        elif option == 'down':
            tmp_speed = instance.anim_speed*2
            instance.anim_speed = tmp_speed if (tmp_speed < 0.1) else 0.1


    def _load_template(self, file_name):
        # kvファイル名の取得
        kv_name = os.path.join(self.curdir, 'data', 'kv_template','{}.kv'.format(file_name).lower())
        instance = Builder.load_file(kv_name)
        return instance

    def _wait_cancel(self):

        if self.threads['load_thumbnails'].is_alive():
            self.load_cancel = True
            self.threads['load_thumbnails'].join()
            self.load_cancel = False

        return
    
    def _reset_mode(self):
        self.item_select_mode = 'normal'

        self.root.ids.favorite.state = 'normal'
        self.root.ids.chapter.state = 'normal'
        self.root.ids.trash.state = 'normal'

        option_layout = self.root.ids.additional_option
        option_layout.clear_widgets()

        self.image_selected[:] = False
        self._update_all_thumbnail_color()

        height = 0
        Animation(height=height, d=.3, t='out_quart').start(option_layout)


    def _keyboard_closed(self):
        print('My keyboard have been closed!')
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        #print('The key', keycode, 'have been pressed')
        #print(' - text is %r' % text)
        #print(' - modifiers are %r' % modifiers)

        if keycode[1] == 'f1':
            self.open_settings()

        # Keycode is composed of an integer + a string
        # If we hit escape, release the keyboard
        if keycode[1] == 'escape':
            keyboard.release()

        sm = self.root.ids.sm
        # ImageView用のキーバインディング
        if sm.current == 'ImageView':
            if keycode[1] == 'left':
                self.change_view_image('previous')
            if keycode[1] in ['right','enter']:
                self.change_view_image('next')
            if keycode[1] == 'backspace':
                self.go_previous_screen()

        # Return True to accept the key. Otherwise, it will be used by
        # the system.
        return True


if __name__ == '__main__':

    logging.debug('main start')

    MyDataBaseApp().run()