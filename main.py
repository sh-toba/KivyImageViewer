#-*- coding: utf-8 -*-
from kivy.config import Config
#Config.set('graphics', 'width', '1024')
#Config.set('graphics', 'height', '768')

import pathlib, os, sys, glob, time, math, threading
from functools import partial
import numpy as np
from itertools import chain

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
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.screenmanager import Screen, FallOutTransition, SlideTransition, RiseInTransition
from kivy.uix.tabbedpanel import TabbedPanelItem, TabbedPanelHeader

import fonts_ja
#from kivy.core.text import LabelBase, DEFAULT_FONT
#from kivy.resources import resource_add_path

# デフォルトに使用するフォントを変更する
#resource_add_path('./fonts')
#LabelBase.register(DEFAULT_FONT, 'mplus-2c-regular.ttf') #日本語が使用できるように日本語フォントを指定する

class JumpPopUp(BoxLayout):
    pass

class FilterItem(BoxLayout):
    text = StringProperty()

class ThumbnailJump(Button):
    pass
    
class ImageButton(ButtonBehavior, Image):
    pass

class DataBaseScreen(Screen):
    fullscreen = BooleanProperty(True)

    def add_widget(self, *args):
        if 'content' in self.ids:
            return self.ids.content.add_widget(*args)
        return super(DataBaseScreen, self).add_widget(*args)


class MyDataBaseApp(App):

    curdir = os.path.dirname(__file__)
    
    max_thumnail = 50 # 配置する最大サムネイル数
    max_jump_button = 9 # 配置するジャンプボタン数
    supported_ext = ["jpg", "png"]
    animation_speed = .4
    allow_stretch = True

    hide_menu = BooleanProperty(False)

    # 読み込んだ画像全体の情報
    image_dir = StringProperty()
    image_list = ListProperty([]) # 読み込んでいる画像ファイルの絶対パス
    image_num = NumericProperty()

    image_selected = []
    image_option = {
        'favorite':[],
        'chapter':[]
    }

    image_select_mode = 'normal' # normal:画像ビューへ, trash:ゴミ箱, favorite:お気に入り選択、chapter:チャプター選択
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
    
    # image_view用
    image_idx = NumericProperty()
    image_file_name = StringProperty()
    image_file_path = StringProperty()

    progress = NumericProperty()

    # thread
    threads = {}
    
    def build(self):
        self.title = 'MyDataBase'
        self.view_size = 1

        sm = self.root.ids.sm
        
        # ThumbnailViewのテンプレート読み込み
        sm.add_widget(self._load_template('ThumbnailView'))
        self.threads['load_thumbnails'] = threading.Thread()

        # ImageViewのテンプレート読み込み
        sm.add_widget(self._load_template('ImageView'))

        # キーボードバインディング
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self.root, 'text')
        if self._keyboard.widget:
            # If it exists, this widget is a VKeyboard object which you can use
            # to change the keyboard layout.
            pass
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def close_popup(self):
        self.popup.dismiss()

    def go_previous_screen(self):

        sm = self.root.ids.sm
        if sm.current == 'ThumbnailView':
            sm.transition = SlideTransition(direction='right', duration=self.animation_speed)
            sm.current = 'InitialScreen'
            self._reset_mode()
            return

        if sm.current == 'ImageView':
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

        elif sm.current is 'ThumbnailView':
            th = TabbedPanelHeader(text='その他')
            filter_items = self._load_template('FilterItems')
            filter_items.ids.fi.add_widget(FilterItem(text='お気に入り'))
            filter_items.ids.fi.add_widget(FilterItem(text='チャプター'))
            th.content = filter_items
            tp.add_widget(th)
            
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


    # ThumbnailViewイベント
    def go_thumbnailview(self, image_dir=None):
        
        # TODO : エラーハンドリング - 不正なパス
        if image_dir is None:
            return

        self.image_dir = os.path.join(self.curdir, image_dir)
        tmp_list = list(chain.from_iterable([glob.glob(os.path.join(self.image_dir, "*." + ext)) for ext in self.supported_ext]))
        self.image_list = [os.path.basename(r) for r in tmp_list]
        self.image_num = len(self.image_list)

        # TODO : エラーハンドリング
        if self.image_num == 0:
            pass
        
        self.image_selected = np.zeros(self.image_num, dtype=bool)
        
        for opt_key in self.image_option.keys():
            self.image_option[opt_key] = np.zeros(self.image_num, dtype=bool)

        # テスト用
        for opt_key in self.image_option.keys():
            for i in range(self.image_num):
                if opt_key is 'favorite':
                    self.image_option[opt_key][i] = ((i % 10) == 0)
                elif opt_key is 'chapter':
                    self.image_option[opt_key][i] = ((i % 23) == 0)

        self._reset_mode()

        sm = self.root.ids.sm
        sm.transition = SlideTransition(direction='left', duration=self.animation_speed)
        sm.current = 'ThumbnailView'

        self.reload_thumbnailview()
        
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
        content = JumpPopUp()
        self.popup = Popup(title='ページ移動', content=content, size_hint=(None, None), size=(300, 150), auto_dismiss=True)
        self.popup.open()

    def jump_thumbnail(self, text):
        self.change_thumbnailview(text)
        self.popup.dismiss()

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


    # 画像選択モード
    def change_mode(self, mode):

        self.image_select_mode = mode
        self.range_selectable = False

        if self.root.ids.sm.current in 'ThumbnailView':
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
                    delete_button = Button(text='削除',size_hint_x=None,width=80, background_color=[0.128, 0.128, 0.128, 1])
                    delete_button.bind(on_release=self.delete_images)
                    option_layout.add_widget(delete_button)

            Animation(height=height, d=.3, t='out_quart').start(option_layout)

    def select_image(self, thumbnail):

        if self.root.ids.sm.current != 'ThumbnailView':
            return

        im_index = thumbnail.im_index

        # イメージビューへ 
        if self.image_select_mode is 'normal':

            self._wait_cancel()

            self.image_file_path = os.path.join(self.image_dir, self.image_list[im_index])
            self.image_file_name = self.image_list[im_index]
            self.image_idx = im_index

            #self._reset_mode() #normalモード以外では移らないのでいらない
            
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
                    
                    if self.image_select_mode is 'trash':
                        self.image_selected[s_index:e_index+1] = True
                    else:
                        self.image_option[self.image_select_mode][s_index:e_index+1] ^= True
                    
                    self.range_select_base = None
                    self._update_all_thumbnail_color()

            # 単一選択
            else:
                if self.image_select_mode is 'trash':
                    self.image_selected[im_index] ^= True
                    thumbnail.is_selected ^= True 
                else:
                    self.image_option[self.image_select_mode][im_index] ^= True
                    if self.image_select_mode is 'favorite':
                        thumbnail.is_favorite ^= True
                    elif self.image_select_mode is 'chapter':
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
            if self.image_select_mode in ['normal', 'trash']:
                tmp_index = self.image_idx + 1
            elif self.image_select_mode in ['favorite','chapter']:
                for i in range(self.image_idx+1, self.image_num):
                    if self.image_option[self.image_select_mode][i]:
                        tmp_index = i
                        break

        elif option is 'previous':
            if self.image_select_mode in ['normal', 'trash']:
                tmp_index = self.image_idx - 1
            elif self.image_select_mode in ['favorite','chapter']:
                for i in reversed(range(0, self.image_idx)):
                    if self.image_option[self.image_select_mode][i]:
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
        self.image_select_mode = 'normal'

        self.root.ids.favorite.state = 'normal'
        self.root.ids.chapter.state = 'normal'
        self.root.ids.trash.state = 'normal'

        option_layout = self.root.ids.additional_option
        option_layout.clear_widgets()

        self.image_selected[:] = False
        self._update_all_thumbnail_color()

        height = 0
        Animation(height=height, d=.3, t='out_quart').start(option_layout)

    def _hide_action_view_item(self):
        
        av_prev = self.root.ids.av_prev
        av_prev.title = ''
        #av_prev.with_previous = False
        #av_prev.app_icon = ''

        #av_tmsize = self.root.ids.av_tmsize
        #av_tmsize.overflow_image = ''

        av_trash = self.root.ids.trash
        av_trash.text = ''

        av_favorite = self.root.ids.favorite
        av_favorite.text = ''

        av_chapter = self.root.ids.chapter
        av_chapter.text = ''

        av_filter = self.root.ids.filter
        av_filter.text = ''



    def _keyboard_closed(self):
        print('My keyboard have been closed!')
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        print('The key', keycode, 'have been pressed')
        print(' - text is %r' % text)
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
    MyDataBaseApp().run()