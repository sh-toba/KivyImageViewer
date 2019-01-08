#-*- coding: utf-8 -*-

from pathlib import Path
import sqlite3, os, copy, glob, time, threading, datetime, shutil, logging
from itertools import chain
from PIL import Image, ImageSequence

LIST_DELIMITER = ';'
sqlite3.dbapi2.converters['DATETIME'] = sqlite3.dbapi2.converters['TIMESTAMP']

class DataBaseManager():
    """
    GUIメインからのデータベース操作をSQLを意識せずに済むようにラッピングする。
    """
    logger = logging.getLogger('MyDBApp') 

    DATABASE_NAME = 'database.sqlite'
    DATA_DIR = 'data'

    SUPPORTED_EXT = ["jpg", "jpeg", "png", "bmp", "gif", "zip"]

    TEMPLATE_MAIN_COLUMN = {
        'Title': 'text primary key',
        'InitialCharacter': 'text',
        'Updated': 'datetime',
        'FileNum': 'Integer',
        'Size': 'Real',
        'IsFavorite': 'Integer',
        'favorite': 'text',
        'chapter': 'text'
    }

    TEMPLATE_TAGS_COLUMN = {
        'Name': 'text primary key',
        'InitialCharacter': 'text',
        'IsFavorite': 'Integer'
    }

    db_root = ''
    data_dir = ''
    record_num = 0

    # ファイル複製スレッド
    copy_progress = {
        'task_num':0,
        'task_index':0,
        'title':'',
        'file_num':0,
        'copied_file':0
        }
    is_cancel = False

    # cursorのスレッド以外で発行されたSQL文を溜め込む
    sql_tasks = []

    dbm_thread_id = 0 

    copy_tasks = []
    file_op_thread = threading.Thread() # ファイル操作用のスレッド

    def __init__(self):
        self.logger.debug('get instance')

    def __del__(self):
        self.logger.debug('delete instance')
        self.close()

    # データベース操作
    def close(self):

        if self.file_op_thread.is_alive():
            self.file_op_thread.join()

        self.cursor.close()
        self.connection.close()
    
    def connect_database(self, db_root):

        db_path = os.path.join(db_root, self.DATABASE_NAME)
        if not os.path.exists(db_path):
            return False

        self.db_root = db_root
        self.data_dir = os.path.join(self.db_root, self.DATA_DIR)

        self.logger.debug('open database')

        self.connection = sqlite3.connect(db_path, detect_types = sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
    
    def create_database(self, db_root, additional_tags={}):
        """
        概要:
            新規データベースを作成する。
        引数:
            db_root: データベースのルートディレクトリ
            additional_tags: ユーザが任意で追加していくタグのdict
                - key:タグ名、value:sqlite内でのデータ型
        返り値:
            db_rootにdatabase.sqliteが存在する場合Falseリターン
        メモ:
        """

        # すでにデータベースがある場合はFalseリターン
        db_path = os.path.join(db_root, self.DATABASE_NAME)
        if os.path.exists(db_path):
            return False

        # データベースとデータ置き場の作成
        self.db_root = db_root
        self.connection = sqlite3.connect(db_path, detect_types = sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
        self.data_dir = os.path.join(self.db_root, self.DATA_DIR)
        if not os.path.exists(self.data_dir):
            os.mkdir(self.data_dir)

        # Mainテーブルを作成する。
        table_name = 'MainTable'
        table_columns = copy.deepcopy(self.TEMPLATE_MAIN_COLUMN)
        table_columns.update(additional_tags)
        tmp_str = ','.join(['{} {}'.format(key, value) for key,value in table_columns.items()]) 
        sql = 'create table if not exists {} ({})'.format(table_name, tmp_str)
        
        self.logger.debug(sql)
        self.cursor.execute(sql)

        # 追加タグ記録用のテーブルを作成する
        for key in additional_tags.keys():
            table_name = key
            tmp_str = ','.join(['{} {}'.format(key, value) for key,value in self.TEMPLATE_TAGS_COLUMN.items()]) 
            sql = 'create table if not exists {} ({})'.format(table_name, tmp_str)
            self.logger.debug(sql)
            self.cursor.execute(sql)

        self.connection.commit()

        return True

    def delete_database(self):
        pass

    # MainTable操作
    def get_record_num(self):
        sql = 'SELECT count(*) FROM MainTable'
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        return result[0][0]

    def insert_records(self, records):
        """
        概要:
            レコードを登録する。
            登録のみでファイルの移動はせず、クラス内のcopy_tasksに追加される。
            別途start_copyでコピータスクを実行する。
            本関数を小分けで使用してタスクを貯めてからまとめて実行もできるはず...
        引数:
            records: 下記の構造を持つ辞書のリスト
                {
                    path:登録ファイル群のフォルダのパス（必須）
                    Title:登録タイトル（レコードの主キー、必須）
                    values_dict:{その他のカラム内容の辞書、任意}
                }
        返り値:
            err_info: 'title: エラー内容'のstringのリスト
        メモ:
            ・err_infoは辞書のほうが使い勝手がよいかも
            ・未実装のエラーハンドリング
                - values_dictの不正なカラム
                - pathとtitleがない場合
            ・上書きができるようにすると色々と幅が広がる
                - 上書きモードと追加モードなどなど
        """

        title_list = self.get_items('Title', convert=True)

        self.copy_tasks = []
        
        err_info = []
        for info in records:

            # 情報の取り出し
            title = info['Title']
            src_path = info['path']
            values_dict = copy.deepcopy(info['values_dict'])
            
            # 同名タイトル
            if title in title_list:
                err_info.append('{} : 同名タイトルがあります。'.format(title))
                break

            # パスの正当性確認
            if not os.path.exists(src_path):
                err_info.append('{} : 該当するフォルダがありません。'.format(title))
                break

            # ファイル一覧取得
            file_list = sorted(list(chain.from_iterable([glob.glob(os.path.join(src_path, "*." + ext)) for ext in self.SUPPORTED_EXT])))

            # ファイルがない場合
            if len(file_list) == 0:
                err_info.append('{} : 該当するファイルがありません。'.format(title))
                break

            # レコードを作成する
            try:
                values_dict['Title'] = title
                sql_tmp, sql_values = self._convert_dict4sql(values_dict)
                sql = 'insert into MainTable {}'.format(sql_tmp)
                self.logger.debug('{} {}'.format(sql, sql_values))
                self.cursor.execute(sql, sql_values)
            except:
                err_info.append((title, 'SQL Insert Error'))
                break

            # ファイルコピーのタスクを作成する
            self.copy_tasks.append({
                'title':title,
                'src_list':file_list,
                'dst_path':os.path.join(self.data_dir, title),
                })

        self.connection.commit()

        return err_info

    def start_copy(self, move_file=False):
        """
        概要:
            insert_recordsで発生したcopy_tasksを別スレッドで実行する。
            レコード内容を更新するsqlをsql_tasksとして溜め込むため、コピー完了後にresolve_sql_tasksの実行が必要。
            スレッドの生存は、file_op_is_aliveで確認できる。
            コピーの進捗状況は、get_copy_progressで取得できる。
        引数:
            move_file:コピーではなくファイルを移動する。
        返り値:
            False：前のスレッドが生きている場合にFalseを返す。
        メモ:
            ・sqlが、cursorを取得したスレッドでしか実行できないので、タスクとしてためている。
                - sqlの実施だけメインスレッドに帰ってきて実行とかできないだろうか...
            ・キャンセル操作への対応
        """

        if self.file_op_thread.is_alive():
            return False

        self.file_op_thread = threading.Thread(target=self._copy_files, args=([move_file]),daemon=False)
        self.file_op_thread.start()

        return True

    def delete_record(self, titles):
        """
        概要:
            指定されたレコードと該当するファイルを削除する。
        引数:
            titles: 削除するレコードのtitleのリスト
        返り値:
            False：前のスレッドが生きている場合にFalseを返す。
        メモ:
            ファイル削除は別スレッドだが、shutil.rmtreeでの一括消去のため進捗は確認できない。
            copyのタスクと同じ形式でまとめたいところ。
        """

        if self.file_op_thread.is_alive():
            return False

        for title in titles:
            sql = 'DELETE FROM MainTable WHERE Title="{}"'.format(title)
            self.logger.debug(sql)
            self.cursor.execute(sql)

        self.file_op_thread = threading.Thread(target=self._delete_files, args=([titles]),daemon=False)
        self.file_op_thread.start()

        self.connection.commit()

        return True

    def update_record(self, title, values_dict):
        """
        登録済みのデータのアップデート
        """
        data_list = []

        for key, value in values_dict.items():
            
            if key is 'Title':
                b_path = os.path.join(self.data_dir, title)
                n_path = os.path.join(self.data_dir, value)
                os.rename(b_path, n_path)

            if type(value) is list:
                tmp_val = LIST_DELIMITER.join([str(i) for i in value])
            else:
                tmp_val = value
            data_list.append('{0}="{1}"'.format(key,tmp_val))

        sql_set_data = ','.join(data_list)
        sql = 'UPDATE MainTable SET {0} WHERE Title="{1}"'.format(sql_set_data, title)
        
        # cursorのスレッドのみ実行可能なため、それ以外はタスクとして溜め込む
        try:
            self.logger.debug(sql)
            self.cursor.execute(sql)
            self.connection.commit()
        except:
            self.logger.debug('before SQL STACKED')
            self.sql_tasks.append(sql) 

    def title_is_exist(self, title):
        sql = 'SELECT COUNT(*) FROM MainTable WHERE Title="{}"'.format(title)
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        return result[0][0] != 0

    def resolve_sql_tasks(self):
        """
        未実行のSQL文を実行する
        """
        for sql in self.sql_tasks:
            self.logger.debug(sql)
            self.cursor.execute(sql)

        self.sql_tasks = []
        self.connection.commit()

    def _copy_files(self, move_file=False):

        # TODO: 中断操作対応

        self.copy_progress['task_num'] = len(self.copy_tasks)

        for t_idx, ctask in enumerate(self.copy_tasks):

            self.copy_progress['task_index'] = t_idx+1

            # 初期設定
            values_dict = {}
            title = ctask['title']
            dst_path = ctask['dst_path']
            if not os.path.exists(dst_path):
                os.mkdir(dst_path)
            file_list = ctask['src_list']

            self.copy_progress['title'] = title
            self.copy_progress['file_num'] = len(file_list)
            self.copy_progress['copied_file'] = 0

            # ファイルコピー - ついでに容量も計算
            values_dict['Size'] = 0
            values_dict['FileNum'] = 0
            for i, file_path in enumerate(file_list):
                 
                _, ext = os.path.splitext(file_path)
                #print(type(ext), ext)

                if ext == '.gif':
                    
                    thum_dir = os.path.join(dst_path, '__thumbnail__')
                    if not os.path.exists(thum_dir):
                        os.mkdir(thum_dir)

                    new_name = str(i).zfill(5)
                    new_path = os.path.join(dst_path, new_name)
                    self._gif_to_zip(file_path, new_path, thum_dir)
                    values_dict['Size'] += os.path.getsize(new_path + '.zip')
                else:
                    new_name = '{0}{1}'.format(str(i).zfill(5), ext)
                    new_path = os.path.join(dst_path, new_name)

                    # TODO: 上書き操作は仮で禁止にしている
                    if not os.path.exists(new_path):
                        if move_file:
                            shutil.move(file_path, new_path)
                        else:
                            shutil.copyfile(file_path, new_path)
                    values_dict['Size'] += os.path.getsize(new_path)
                values_dict['FileNum'] += 1
                self.copy_progress['copied_file'] += 1

            values_dict['Size'] /= (1024*1024) # MB変換
            values_dict['Updated'] = datetime.datetime.now()

            # データベース情報更新
            self.update_record(title, values_dict=values_dict)

            self.logger.debug('Copy Operation Finished')

    def _delete_files(self, titles):

        for title in titles:
            del_path = os.path.join(self.data_dir, title)
            if os.path.exists(del_path):
                shutil.rmtree(del_path)

        self.logger.debug('Delete Operation Finished')

    def file_op_is_alive(self):
        return self.file_op_thread.is_alive()

    def get_copy_progress(self):
        return copy.deepcopy(self.copy_progress)

    def get_items(self, col_name, title=None, convert=False):
        """
        col_namesのリストに対するSELECT結果（tuple）を返す。
        covertをTrueにすると、tupleから変換して返す。
        　・col_nameがstrならlist
        　・col_nameがlistならcol_nameをkeyとしたdict
        """

        if type(col_name) is list:
            sql = 'SELECT {} FROM MainTable'.format(','.join(col_name))
        elif type(col_name) is str:
            sql = 'SELECT {} FROM MainTable'.format(col_name)
        else:
            return []

        if not title is None:
            sql += ' WHERE Title="{}"'.format(title)

        self.logger.debug(sql)
        ret = self.cursor.execute(sql)

        if convert:
            if type(col_name) is list:
                tmp_dict = {}
                for cl in col_name:
                    tmp_dict[cl] = []
                for row in ret.fetchall():
                    for i, cl in enumerate(col_name):
                        tmp_dict[cl].append(self._convert_list(row[i]))
                return tmp_dict
            elif type(col_name) is str:
                tmp_list = []
                for row in ret.fetchall():
                    tmp_list += self._convert_list(row[0])
                return tmp_list
        else:
            return ret.fetchall()

    def get_titles(self, filter_option={}, init_chars=[], enable_or=False):

        col_names = ['Title', 'FileNum', 'IsFavorite', 'InitialCharacter'] + list(filter_option.keys())

        sql = 'SELECT {} FROM MainTable ORDER BY Updated DESC'.format(','.join(col_names))
        ret = self.cursor.execute(sql)
        
        title_list = []
        for row in ret.fetchall():

            if len(init_chars) != 0:
                if not row[3] in init_chars:
                    continue

            if len(filter_option.keys()) == 0:
                flag = True
            else:            
                flag = False if enable_or else True
                for i in range(4, len(col_names)):
                    # 値取得
                    ref_val = self._convert_list(row[i])
                    key = col_names[i]
                    f_val = filter_option[key]
                    for fv in f_val:
                        if enable_or:
                            flag |= (fv in ref_val)
                        else:
                            flag &= (fv in ref_val)
            if flag:
                title_list.append((row[0],row[1],row[2]))

        return title_list

    def get_image_list(self, title):

        image_dir = os.path.join(self.data_dir, title)

        if not os.path.exists(image_dir):
            return '', []

        #登録時に拡張子はフィルタされるのでファイルすべてを取得しているが、早くなるかは不明
        #tmp_list = sorted(glob.glob(os.path.join(image_dir, "*")))
        #image_list = [os.path.basename(r) for r in tmp_list]

        tmp_list = sorted(list(chain.from_iterable([glob.glob(os.path.join(image_dir, "*." + ext)) for ext in self.SUPPORTED_EXT])))
        image_list = [os.path.basename(r) for r in tmp_list]

        return image_dir, image_list


    # 追加項目操作
    def get_additional_tags(self):
        """
        ユーザ作成のタグ一覧の取得
        (= MainTable以外のテーブル名の一覧)
        """
        table_list = []
        self.cursor.execute("select * from sqlite_master where type='table'")
        for x in self.cursor.fetchall():
            if not x[1] is 'MainTable':
                table_list.append(x[1])
        return table_list

    """
    def get_tag_items(self, table, convert=False):

        sql = 'SELECT Name FROM {}'.format(table)
        self.logger.debug(sql)
        ret = self.cursor.execute(sql)

        if convert:
            tmp_list = []
            for row in ret.fetchall():
                tmp_list.append(row[0])
            return tmp_list
        else:
            return ret.fetchall()
    """

    def add_tag(self, tag, values):
        """
        新規タグを追加する
            tagはMainTable内に存在するタグ名
            valuesは追加するタグ内容のリスト[Name, InitialCharacter]
        Nameが重複した場合はFalseリターン
        """
        try:
            sql = 'insert into {}(Name, InitialCharacter) VALUES(?,?)'.format(tag)
            self.logger.debug('{} {}'.format(sql, values))
            self.cursor.execute(sql, values)
            self.connection.commit()
            return True
        except:
            return False

    def update_tag(self, tag_table, tag_name, values_dict):
        """
        タグの情報を変更する。
        """
        data_list = []

        for key, value in values_dict.items():

            if type(value) is list:
                tmp_val = LIST_DELIMITER.join([str(i) for i in value])
            else:
                tmp_val = value
            data_list.append('{0}="{1}"'.format(key,tmp_val))

        sql_set_data = ','.join(data_list)
        sql = 'UPDATE {0} SET {1} WHERE Name="{2}"'.format(tag_table, sql_set_data, tag_name)

        try:
            self.logger.debug(sql)
            self.cursor.execute(sql)
            self.connection.commit()
        except:
            return False

        # タグ名を変更した場合 - MainTableにも反映する
        if 'Name' in values_dict.keys():
            old_name = tag_name
            new_name = values_dict['Name']
            update_list = [] # tuple(Title, NewList)

            sql = 'SELECT Title,{} FROM MainTable'.format(tag_table)
            ret = self.cursor.execute(sql)

            for row in ret.fetchall():
                title = row[0]
                tag_list = self._convert_list(row[1])
                if old_name in tag_list:
                    new_list = [new_name if t == old_name else t for t in tag_list]
                    update_list.append((title,{tag_table:copy.deepcopy(new_list)}))
            
            for ul in update_list:
                self.update_record(title=ul[0],values_dict=ul[1])

        return True

    def delete_tags(self, tag, names):
        for name in names:
            sql = 'DELETE FROM {} WHERE Name="{}"'.format(tag, name)
            self.logger.debug(sql)
            self.cursor.execute(sql)
        self.connection.commit()
        return

    def get_tag_list(self, tag):
        sql = 'SELECT * FROM {}'.format(tag)
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def get_tag_items_with_num(self, tag_table, init_chars=[]):
        """
        タグ内容に該当する項目数をカウントして返す。
        リスト項目があるためfor文ループをしている
        """
        sql = 'SELECT Name,InitialCharacter,IsFavorite FROM {}'.format(tag_table)

        tag_info = {}
        self.cursor.execute(sql)
        for row in self.cursor.fetchall():
            if len(init_chars) != 0:
                if row[1] in init_chars:
                    tag_info[row[0]] = [0, row[2]]
            else:
                tag_info[row[0]] = [0, row[2]]

        sql = 'SELECT {} FROM MainTable'.format(tag_table)
        self.cursor.execute(sql)
        for row in self.cursor.fetchall():
            item_list = self._convert_list(row[0])
            for il in item_list:
                if il in tag_info.keys():
                    tag_info[il][0] += 1

        return tag_info
        
    
    def get_tag_items(self, table, col_name, name=None, convert=False):
        """
        get_itemのタグ用のテーブル版
        """

        if type(col_name) is list:
            sql = 'SELECT {} FROM {}'.format(','.join(col_name), table)
        elif type(col_name) is str:
            sql = 'SELECT {} FROM {}'.format(col_name, table)
        else:
            return []

        if not name is None:
            sql += ' WHERE Name="{}"'.format(name)

        self.logger.debug(sql)
        ret = self.cursor.execute(sql)

        if convert:
            if type(col_name) is list:
                tmp_dict = {}
                for cl in col_name:
                    tmp_dict[cl] = []
                for row in ret.fetchall():
                    for i, cl in enumerate(col_name):
                        tmp_dict[cl].append(self._convert_list(row[i]))
                return tmp_dict
            elif type(col_name) is str:
                tmp_list = []
                for row in ret.fetchall():
                    tmp_list += self._convert_list(row[0])
                return tmp_list
        else:
            return ret.fetchall()


    def show_all(self):
        sql = 'SELECT * FROM MainTable'
        ret = self.cursor.execute(sql)
        for row in ret.fetchall():
            print(row)

    def _convert_dict4sql(self, input_dict):
        """
        辞書形式のデータをSQLのVALUES文に対応させる。
        プレースホルダー型。
        """
        
        key_list = []
        tmp_list = []
        values = []

        for key, value in input_dict.items():
            key_list.append(key)
            tmp_list.append('?')

            if type(value) is list:
                values.append(LIST_DELIMITER.join([str(i) for i in value]))
            else:
                values.append(value)

        key_list_str = ','.join(key_list)
        tmp_list_str = ','.join(tmp_list)

        sql = '({0}) values ({1})'.format(key_list_str, tmp_list_str)
        sql_values = tuple(values)

        return sql, sql_values

    def _convert_list(self, src):
        if type(src) is str:
            tmp_list = src.split(LIST_DELIMITER)
            return tmp_list
        else:
            return list([src])

    def _gif_to_zip(self, src_gif, dst_dir, thum_dir):
        
        if not os.path.exists(dst_dir):
            os.mkdir(dst_dir)

        gif = Image.open(src_gif)
        for i, f in enumerate(ImageSequence.Iterator(gif)):
            if i == 0:
                thum_name = os.path.basename(dst_dir) + '.png'
                thum_path = '{}/{}'.format(thum_dir, thum_name)
                f.save(thum_path)
        
            img_name = str(i).zfill(3) + ".png"
            img_path = '{}/{}'.format(dst_dir, img_name)
            #print(img_path)
            f.save(img_path)

        """
        thum_name = os.path.basename(dst_dir)
        for f in frames:
            name = '{}/{}{}'.format(thum_dir, thum_name, '.gif')
            f.save(name)
            break
        """

        #frames = self._get_gif_frames(src_gif)
        #self._write_gif_frames(frames, src_gif, dst_dir)
        shutil.make_archive(dst_dir, 'zip', dst_dir)
        shutil.rmtree(dst_dir)

    def _get_gif_frames(self, path):
        '''パスで指定されたファイルのフレーム一覧を取得する
        '''
        im = Image.open(path)
        return (frame.copy() for frame in ImageSequence.Iterator(im))

    def _write_gif_frames(self, frames, name_original, destination):
        '''フレームを別個の画像ファイルとして保存する
        '''
        path = Path(name_original)

        stem = path.stem
        extension = path.suffix

        # 出力先のディレクトリが存在しなければ作成しておく
        dir_dest = Path(destination)
        
        if not dir_dest.is_dir():
            dir_dest.mkdir(0o700)
            #print('Destionation directory is created: "{}".'.format(destination))


        for i, f in enumerate(frames):
            idx = str(i+1).zfill(3)
            name = '{}/{}-{}{}'.format(destination, stem, idx, extension)
            f.save(name)
            #print('A frame is saved as "{}".'.format(name))
