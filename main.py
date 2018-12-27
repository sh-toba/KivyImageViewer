#-*- coding: utf-8 -*-
from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '768')

import pathlib, os, sys, glob, time, math, threading
from functools import partial
import numpy as np

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

import fonts_ja
#from kivy.core.text import LabelBase, DEFAULT_FONT
#from kivy.resources import resource_add_path

# デフォルトに使用するフォントを変更する
#resource_add_path('./fonts')
#LabelBase.register(DEFAULT_FONT, 'mplus-2c-regular.ttf') #日本語が使用できるように日本語フォントを指定する

class JumpPopUp(BoxLayout):
    text = StringProperty()
    yes = ObjectProperty(None)
    no = ObjectProperty(None)

class ThumbnailJump(Button):
    pass
    
class ImageButton(ButtonBehavior, Image):
    pass

class DataBaseScreen(Screen):
    fullscreen = BooleanProperty(False)

    def add_widget(self, *args):
        if 'content' in self.ids:
            return self.ids.content.add_widget(*args)
        return super(DataBaseScreen, self).add_widget(*args)


class MyDataBaseApp(App):

    curdir = os.path.dirname(__file__)

    db_root = r'db'
    test_dir = 'sub'

    image_color_def = ListProperty([1.0,1.0,1.0,1.0])
    image_color_selected = ListProperty([0.0,0.6,0.8,0.5])
    image_color_base = ListProperty([0.0,0.8,0.6,0.5])
    
    max_thumnail = 50 # 配置する最大サムネイル数
    max_jump_button = 9 # 配置するジャンプボタン数

    # thumbnailview用
    image_list = ListProperty([]) # 読み込んでいる画像ファイルの絶対パス
    image_num = NumericProperty()

    image_selected = []
    image_select_mode = 0
    range_select_base = None
    view_size = NumericProperty()

    divided_num = NumericProperty()
    divided_index = None
    divided_slice = ListProperty([0,0])
    thumbnail_num  = 0

    load_active = False
    load_cancel = False
    update_count = 0
    
    # image_view用
    image_idx = NumericProperty()
    image_file = StringProperty()

    progress = NumericProperty()

    # thread
    threads = {}
    
    def build(self):
        self.title = 'MyDataBase'
        self.screens = {}

        sm = self.root.ids.sm
        
        # 
        self.view_size = 1
        
        # 先に作ってしまう作戦
        screen = self._load_template('ThumbnailView')
        #for i in range(self.max_thumnail_num):
            #print('create thumbnail', i)
            #thumbnail = self._load_template('Thumbnail')
            #thumbnail.id = 'thumbnail-{}'.format(i)
            #thumbnail.im_index = i
            #thumbnail.im_source = ''
            #self.screens['ThumbnailView'].ids.thumbnails.add_widget(thumbnail)
            #screen.ids.thumbnails.add_widget(thumbnail)
        sm.add_widget(screen)

        self.threads['load_thumbnails'] = threading.Thread()

        #
        sm.add_widget(self._load_template('ImageView'))

        # 
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self.root, 'text')
        if self._keyboard.widget:
            # If it exists, this widget is a VKeyboard object which you can use
            # to change the keyboard layout.
            pass
        self._keyboard.bind(on_key_down=self._on_keyboard_down)


    def _keyboard_closed(self):
        print('My keyboard have been closed!')
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        #print('The key', keycode, 'have been pressed')
        #print(' - text is %r' % text)
        #print(' - modifiers are %r' % modifiers)

        # Keycode is composed of an integer + a string
        # If we hit escape, release the keyboard
        if keycode[1] == 'escape':
            keyboard.release()

        sm = self.root.ids.sm
        # ImageView用のキーバインディング
        if sm.current == 'ImageView':
            if keycode[1] == 'left':
                self.go_previous_image()
            if keycode[1] in ['right','enter']:
                self.go_next_image()
            if keycode[1] == 'backspace':
                self.go_previous_screen()

        # Return True to accept the key. Otherwise, it will be used by
        # the system.
        return True

    def close_popup(self):
        self.popup.dismiss()

    def go_previous_screen(self):
        sm = self.root.ids.sm
        if sm.current == 'ImageView':
            sm.transition = SlideTransition(direction='right')
            sm.current = 'ThumbnailView'
            #sm.switch_to(self.screens['ThumbnailView'], direction='right')

    def go_thumbnailview(self):
        
        self.image_list = glob.glob(os.path.join(self.db_root, self.test_dir, '*.jpg'))

        #self.image_list = ListProperty(image_list)
        #self.image_list.sort()
        self.image_num = len(self.image_list)

        self.image_selected = np.zeros(self.image_num, dtype=bool)

        # 
        self.divided_index = 0
        self.divided_num = math.ceil(self.image_num / self.max_thumnail)
        
        # ジャンプボタンの作成
        layout = self.root.ids.sm.get_screen('ThumbnailView').ids.jump_layout

        # preveous jump
        layout.add_widget(ThumbnailJump(text='<'))
        if self.max_jump_button >= self.divided_num:
            for i in range(self.divided_num):
                layout.add_widget(ThumbnailJump(text='{}'.format(i+1)))
        else:
            for i in range(self.max_jump_button-2):
                layout.add_widget(ThumbnailJump(text='{}'.format(i+1)))
            layout.add_widget(ThumbnailJump(text='...'))
            layout.add_widget(ThumbnailJump(text='{}'.format(self.divided_num)))

        # next jump
        layout.add_widget(ThumbnailJump(text='>'))

        # adjust layout
        layout.width = 48 * len(layout.children) #+ 5 * (len(layout.children)+1)

        #av = self.root.ids.av
        #av.add_widget(self._load_template('ThumbnailAction'))

        sm = self.root.ids.sm
        #sm.switch_to(screen, direction='left')
        sm.transition = SlideTransition(direction='left')
        sm.current = 'ThumbnailView'

        self.reload_thumbnails(layout.children[-2])

    def update_jump_btns(self):

        jump_btns = list(reversed(self.root.ids.sm.get_screen('ThumbnailView').ids.jump_layout.children))
        
        if self.max_jump_button < self.divided_num:
            change_num = self.max_jump_button - 2
            if self.divided_index < change_num:
                jump_btns[-3].text = '...'
                jump_btns[-2].text = '{}'.format(self.divided_num)
                for i, jump_btn in enumerate(jump_btns[1:-3]):
                    jump_index = i+1
                    jump_btn.text = '{}'.format(jump_index)

            elif self.divided_index > (self.divided_num - change_num + 1):
                jump_btns[2].text = '...'
                jump_btns[1].text = '1'
                for i, jump_btn in enumerate(jump_btns[3:-1]):
                    jump_index = self.divided_num - (change_num-i) + 1
                    jump_btn.text = '{}'.format(jump_index)

            else:
                change_num -= 2
                jump_btns[1].text = '1'
                jump_btns[2].text = '...'
                jump_btns[-3].text = '...'
                jump_btns[-2].text = '{}'.format(self.divided_num)

                jump_btns_sub = jump_btns[3:-3]
                for i, diff in enumerate(range(int(-change_num/2), math.ceil(change_num/2))):
                    jump_index = self.divided_index + diff
                    jump_btns_sub[i].text = '{}'.format(jump_index)

        for jump_btn in jump_btns[1:-1]:
            if jump_btn.text.isdecimal():
                if self.divided_index == int(jump_btn.text):
                    jump_btn.background_color = [0.0, 0.5, 0.8, 1.0]
                else:
                    jump_btn.background_color = [0.6, 0.6, 0.6, 0.8]

    def open_jump_popup(self):
        content = JumpPopUp()
        self.popup = Popup(title="ページ移動", content=content, size_hint=(None, None), size=(400, 400), auto_dismiss=True)
        self.popup.open()

    def reload_thumbnails(self, jump_btn):

        current_idx = self.divided_index
        jump_text = jump_btn.text
        
        if jump_text.isdecimal():
            next_index = int(jump_text)
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
    
        if current_idx == next_index:
            return

        self._wait_cancel()

        self.divided_index = next_index

        st_idx = (self.divided_index-1) * self.max_thumnail
        ed_idx = st_idx + self.max_thumnail-1
        if ed_idx >= self.image_num:
            ed_idx = self.image_num-1
        self.divided_slice[0] = st_idx
        self.divided_slice[1] = ed_idx
        self.thumbnail_num = ed_idx - st_idx + 1 

        self.update_jump_btns()

        #return # テスト用

        # 既存サムネイルの削除
        # TODO: 他のやり方のほうが良いかも
        self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails.clear_widgets()

        self.threads['load_thumbnails'] = threading.Thread(target=self.add_thumbnails, daemon=True)
        self.threads['load_thumbnails'].start()

        #self.thread["update_thumb"] = threading.Thread(target=self.update_thumbnailview)
        #self.thread["update_thumb"].start()


    def add_thumbnails(self):
        time.sleep(0.5)
        
        self.load_active = False
        screen = self.root.ids.sm.get_screen('ThumbnailView')

        for i, idx in enumerate(range(self.divided_slice[0], self.divided_slice[1]+1)):

            if self.load_cancel:
                return

            while(self.load_active):
                pass
            
            thumbnail = self._load_template('Thumbnail')
            thumbnail.index = i
            thumbnail.im_index = idx

            """
            thumbnail.im_source = self.image_list[idx]
            if self.image_selected[idx]:
                thumbnail.im_color = self.image_color_selected
            else:
                thumbnail.im_color = self.image_color_def
            """

            screen.ids.thumbnails.add_widget(thumbnail)
            
            self.load_active = True
            Clock.schedule_once(self.update_thumbnailview)

            self.progress = ((i+1) / self.thumbnail_num) * 100

        return

    def update_thumbnailview(self, dt):
        
        try:
            #thumbnails[0].ids.image.reload()
            thumbnail = self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails.children[0]
            thumbnail.im_source = self.image_list[thumbnail.im_index]
            if self.image_selected[thumbnail.im_index]:
                thumbnail.im_color = self.image_color_selected
            else:
                thumbnail.im_color = self.image_color_def
            #print('reload image', thumbnails[0].im_index)
        finally:
            self.load_active = False
            return
            #print('update end')

    def go_select_mode(self, range_selectable):
        
        if self.root.ids.sm.current != 'ThumbnailView':
            return

        if range_selectable:
            self.image_select_mode = 2
        else:
            self.image_select_mode = 1

    def select_image(self, thumbnail):

        im_index = thumbnail.im_index

        # イメージビューへ 
        if self.image_select_mode == 0:

            self._wait_cancel()

            self.image_file = self.image_list[im_index]
            self.image_idx = im_index
            
            sm = self.root.ids.sm
            sm.transition = RiseInTransition()
            sm.current = 'ImageView'
        
        # 画像選択モード
        else:

            # 単一選択
            if self.image_select_mode == 1:
                im_selected = not self.image_selected[im_index]
                if im_selected:
                    thumbnail.im_color = self.image_color_selected
                else:
                    thumbnail.im_color = self.image_color_def
                self.image_selected[im_index] = im_selected

            # 複数選択
            if self.image_select_mode == 2:

                if self.range_select_base is None:
                    thumbnail.im_color = self.image_color_base
                    self.range_select_base = im_index

                else:
                    if self.range_select_base < im_index:
                        s_index = self.range_select_base
                        e_index = im_index
                    else:
                        s_index = im_index
                        e_index = self.range_select_base

                    self.image_selected[s_index:e_index+1] = True
                    self.range_select_base = None
                    self.update_all_thumbnail_color()

        return

    def update_all_thumbnail_color(self):
        thumbnails = self.root.ids.sm.get_screen('ThumbnailView').ids.thumbnails
        for child in sorted(thumbnails.children, key=lambda x:x.im_index):
            if self.image_selected[child.im_index]:
                child.im_color = self.image_color_selected
            else:
                child.im_color = self.image_color_def


    def select_all_image(self):

        if self.root.ids.sm.current != 'ThumbnailView':
            return

        self.image_select_mode = 1
        self.image_selected[:] = True
        self.update_all_thumbnail_color()
        

    def exit_select_mode(self):

        if self.root.ids.sm.current != 'ThumbnailView':
            return

        self.image_select_mode = 0
        self.image_selected[:] = False
        self.update_all_thumbnail_color()


    def go_previous_image(self):
        if(self.image_idx == 0):
            return
        self.image_idx -= 1
        self.image_file = self.image_list[self.image_idx]

        return

    def go_next_image(self):
        if(self.image_idx == (self.image_num-1)):
            return
        self.image_idx += 1
        self.image_file = self.image_list[self.image_idx]

        return

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

        #if self.load_active :
            #print('load cancelled')
            #self.load_cancel = True
            #time.sleep(1)
            #self.load_cancel = False
        return

if __name__ == '__main__':
    MyDataBaseApp().run()