#-*- coding: utf-8 -*-

from pathlib import Path
import sqlite3, os, copy, glob, time, threading, datetime, shutil, logging, json
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
    OPTION_NAME = 'option.json'

    FILE_ENCODING = 'utf-8'

    DATA_DIR = 'data'
    TAG_IMAGE_DIR = 'tag_image'
    BACKUP_DIR = 'backup'
    FILE_NUMBER_OF_DIGITS = 5

    SUPPORTED_EXT = ["jpg", "jpeg", "png", "bmp", "gif", "zip"]

    TEMPLATE_MAIN_COLUMN = {
        'Title': 'text primary key',
        'InitialCharacter': 'text',
        'Updated': 'datetime',
        'FileNum': 'Integer',
        'Size': 'Real',
        'Link':'text',
        'IsFavorite': 'Integer',
        'favorite': 'text',
        'chapter': 'text'
    }

    TEMPLATE_TAGS_COLUMN = {
        'Name': 'text primary key',
        'InitialCharacter': 'text',
        'IsFavorite': 'Integer',
        'Link': 'text',
        'Image': 'text'
    }

    db_root = ''
    data_dir = ''
    tag_dir = ''

    record_num = 0

    # ファイル複製スレッド
    file_op_progress = {
        'task_num':0,
        'task_index':0,
        'title':'',
        'file_num':0,
        'done_file':0
        }
    is_cancel = False

    # cursorのスレッド以外で発行されたSQL文を溜め込む
    sql_tasks = []

    dbm_thread_id = 0 

    file_op_tasks = []
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
    
    def database_is_exist(self, db_root):
        db_path = os.path.join(db_root, self.DATABASE_NAME)
        return os.path.exists(db_path)

    def connect_database(self, db_root):

        db_path = os.path.join(db_root, self.DATABASE_NAME)
        if not os.path.exists(db_path):
            return False

        self.db_root = db_root
        self.data_dir = os.path.join(self.db_root, self.DATA_DIR)
        self.tag_dir = os.path.join(self.db_root, self.TAG_IMAGE_DIR)

        self.logger.debug('open database')

        self.connection = sqlite3.connect(db_path, detect_types = sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()

        opt_name = os.path.join(self.db_root, self.OPTION_NAME)
        with open(opt_name, 'r', encoding=self.FILE_ENCODING) as opt_file:
            max_asign_num = json.load(opt_file)

        return max_asign_num
    
    def create_database(self, db_root, option={}):
        """
        概要:
            新規データベースを作成する。
        引数:
            db_root: データベースのルートディレクトリ
            additional_tags: ユーザが任意で追加していくタグのdict
                - key:タグ名、value:tuple(sqlite内でのデータ型, 最大登録数)
        返り値:
            db_rootにdatabase.sqliteが存在する場合Falseリターン
        メモ:
        """

        # すでにデータベースがある場合はFalseリターン
        db_path = os.path.join(db_root, self.DATABASE_NAME)
        if os.path.exists(db_path):
            return False

        # オプションの分離
        additional_tags = {}
        max_asign_num = {}
        for key, value in option.items():
            additional_tags[key] = value[0]
            max_asign_num[key] = value[1]

        # データベースとデータ置き場の作成
        self.db_root = db_root
        self.connection = sqlite3.connect(db_path, detect_types = sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
        
        self.data_dir = os.path.join(self.db_root, self.DATA_DIR)
        if not os.path.exists(self.data_dir):
            os.mkdir(self.data_dir)
        
        self.tag_dir = os.path.join(self.db_root, self.TAG_IMAGE_DIR)
        if not os.path.exists(self.tag_dir):
            os.mkdir(self.tag_dir)

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

        opt_name = os.path.join(self.db_root, self.OPTION_NAME)
        with open(opt_name, 'w', encoding=self.FILE_ENCODING) as opt_file:
            json.dump(max_asign_num, opt_file)

        self.connection.commit()

        return True

    def delete_database(self):
        self.close()


    # MainTable操作
    def get_db_info(self):
        size_list = self.get_items('Size', convert=True)
        num = len(size_list)
        if num == 0:
            sum_size = 0
        else:
            sum_size = sum(size_list)
        return num, sum_size

    def insert_records(self, records, move_file=False):
        """
        概要:
            レコードを登録する。
            登録のみでファイルの移動はせず、クラス内のfile_op_tasksに追加される。
            別途start_file_operationでコピータスクを実行する。
            本関数を小分けで使用してタスクを貯めてからまとめて実行もできるはず...
        引数:
            records: 下記の構造を持つ辞書のリスト
                {
                    path:登録ファイル群のフォルダのパス（必須）
                    Title:登録タイトル（レコードの主キー、必須）
                    values_dict:{その他のカラム内容の辞書、任意}
                }
            move_file:コピーではなくファイルを移動する。
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

        op_mode = 'move' if move_file else 'copy'
        title_list = self.get_items('Title', convert=True)

        self.file_op_tasks = []
        
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
            file_list = self.search_files(src_path)
            #file_list = sorted(list(chain.from_iterable([glob.glob(os.path.join(src_path, "*." + ext)) for ext in self.SUPPORTED_EXT])))

            # ファイルがない場合
            if len(file_list) == 0:
                err_info.append('{} : 該当するファイルがありません。'.format(title))
                break

            # レコードを作成する
            try:
                values_dict['Title'] = title
                values_dict['FileNum'] = 0
                values_dict['Size'] = 0.0
                values_dict['Link'] = ''
                values_dict['IsFavorite'] = 0
                values_dict['favorite'] = []
                values_dict['chapter'] = []
                sql_tmp, sql_values = self._convert_dict4sql(values_dict)
                sql = 'insert into MainTable {}'.format(sql_tmp)
                self.logger.debug('{} {}'.format(sql, sql_values))
                self.cursor.execute(sql, sql_values)
            except:
                err_info.append((title, 'SQL Insert Error'))
                break

            # ファイルコピーのタスクを作成する
            self.file_op_tasks.append({
                'operation':op_mode,
                'title':title,
                'src_list':file_list,
                'dst_path':os.path.join(self.data_dir, title),
                'init_num':0,
                'init_size':0.0
                })

        self.connection.commit()

        return err_info

    def add_files(self, title, file_list):

        if len(file_list) == 0:
            return False

        self.file_op_tasks = []

        init_info = self.get_items(['FileNum','Size'], title=title)

        # ファイルコピーのタスクを作成する
        self.file_op_tasks.append({
            'operation':'copy',
            'title':title,
            'src_list':sorted(file_list),
            'dst_path':os.path.join(self.data_dir, title),
            'init_num':init_info[0][0],
            'init_size':init_info[0][1]
            })
        
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

        self.file_op_thread = threading.Thread(target=self._delete_titles, args=([titles]),daemon=False)
        self.file_op_thread.start()

        self.connection.commit()

        return True

    def delete_files(self, title,file_idx):
        """
        概要:
        引数:
        返り値:
        メモ:
        """
        if len(file_idx) == 0:
            return False

        self.file_op_tasks = []

        init_info = self.get_items(['FileNum','Size','favorite','chapter'], title=title, convert=True)

        init_favorite = []
        for i in init_info['favorite'][0]:
            if i.isdecimal():
                init_favorite.append(int(i))
        init_chapter = []
        for i in init_info['chapter'][0]:
            if i.isdecimal():
                init_chapter.append(int(i))

        # ファイルコピーのタスクを作成する
        self.file_op_tasks.append({
            'operation':'delete',
            'title':title,
            'src_list':sorted(file_idx),
            'dst_path':os.path.join(self.data_dir, title),
            'init_num':init_info['FileNum'][0][0],
            'init_size':init_info['Size'][0][0],
            'init_favorite': copy.deepcopy(init_favorite),
            'init_chapter':copy.deepcopy(init_chapter)
            })

        return True

    def start_file_operation(self):
        """
        概要:
            insert_recordsで発生したfile_op_tasksを別スレッドで実行する。
            レコード内容を更新するsqlをsql_tasksとして溜め込むため、コピー完了後にresolve_sql_tasksの実行が必要。
            スレッドの生存は、file_op_is_aliveで確認できる。
            コピーの進捗状況は、get_file_op_progressで取得できる。
        引数:
        返り値:
            False：前のスレッドが生きている場合にFalseを返す。
        メモ:
            ・sqlが、cursorを取得したスレッドでしか実行できないので、タスクとしてためている。
                - sqlの実施だけメインスレッドに帰ってきて実行とかできないだろうか...
            ・キャンセル操作への対応
        """

        if self.file_op_thread.is_alive():
            return False

        self.file_op_thread = threading.Thread(target=self._run_file_operation,daemon=False)
        self.file_op_thread.start()

        return True

    def sort_files(self, title,ref_index, insert_index):

        if len(insert_index) == 0:
            return

        title_dir, file_list = self.get_file_list(title)
        init_info = self.get_items(['favorite','chapter'], title=title, convert=True)

        init_favorite = set([])
        for i in init_info['favorite'][0]:
            if i.isdecimal():
                init_favorite.add(int(i))
        init_chapter = set([])
        for i in init_info['chapter'][0]:
            if i.isdecimal():
                init_chapter.add(int(i))

        # 対象範囲のインデックスをすべて取得
        tmp_set = set(insert_index) | set([ref_index])
        trg_idx = set(range(min(tmp_set),max(tmp_set)+1))
        # 入れ替え対象のインデックスを除く, リスト化して指定位置に挿入
        new_order = sorted(trg_idx ^ insert_index)
        ref_pos = new_order.index(ref_index)
        new_order[ref_pos:ref_pos] = sorted(insert_index)

        # ソート１ - 元ファイルをいったん別名にして避難しつつ、ファイル名変更タスクの作成
        old_order = sorted(trg_idx)
        sort_task = []
        new_favorite = set([])
        new_chapter = set([])
        for i, old_idx in enumerate(new_order):

            new_idx = old_order[i]
            if old_idx == new_idx:
                continue

            if old_idx in init_favorite:
                init_favorite.remove(old_idx)
                new_favorite.add(new_idx)
            if old_idx in init_chapter:
                init_chapter.remove(old_idx)
                new_chapter.add(new_idx)

            fname = file_list[old_idx]
            old_idx_str, ext = os.path.splitext(fname) # インデックスと拡張子に分解

            old_path = os.path.join(title_dir, fname)
            tmp_path = os.path.join(title_dir, '_' + fname)
            os.rename(old_path, tmp_path)
            #print('{} -> {}'.format(old_path, tmp_path))

            new_idx_str = str(new_idx).zfill(self.FILE_NUMBER_OF_DIGITS)
            new_path = os.path.join(title_dir, new_idx_str + ext)

            sort_task.append((tmp_path, new_path))

            if ext == '.zip':
                old_thum_path = os.path.join(title_dir, '__thumbnail__', old_idx_str + '.png')
                tmp_thum_path = os.path.join(title_dir, '__thumbnail__', '_' + old_idx_str + '.png')
                os.rename(old_thum_path, tmp_thum_path)
                #print('{} -> {}'.format(old_thum_path, tmp_thum_path))
                
                new_thum_path = os.path.join(title_dir, '__thumbnail__', new_idx_str + '.png')
                sort_task.append((tmp_thum_path, new_thum_path))

        # ソート２ - ファイル名変更の実施
        for stask in sort_task:
            os.rename(stask[0], stask[1])
            #print('{} -> {}'.format(stask[0], stask[1]))

        new_favorite |= init_favorite
        new_chapter |= init_chapter

        # データベースの情報変更
        values_dict = {}
        values_dict['favorite'] = sorted(new_favorite)
        values_dict['chapter'] = sorted(new_chapter)
        #print(values_dict)

        self.update_record(title, values_dict=values_dict)

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


    def _run_file_operation(self):

        # TODO: 中断操作対応

        self.file_op_progress['task_num'] = len(self.file_op_tasks)

        for t_idx, ftask in enumerate(self.file_op_tasks):

            # 初期設定
            op_mode = ftask['operation']
            title = ftask['title']
            trg_path = ftask['dst_path']
            src_list = ftask['src_list']
            idx_offset = ftask['init_num']
            
            values_dict = {}
            values_dict['FileNum'] = ftask['init_num']
            values_dict['Size'] = ftask['init_size']

            self.file_op_progress['task_index'] = t_idx+1
            self.file_op_progress['title'] = title
            self.file_op_progress['file_num'] = len(src_list)
            self.file_op_progress['done_file'] = 0

            if op_mode in ['move', 'copy']:

                if not os.path.exists(trg_path):
                    os.mkdir(trg_path)

                for i, file_path in enumerate(src_list):
                    _, ext = os.path.splitext(file_path)
                    new_name = str(i + idx_offset).zfill(self.FILE_NUMBER_OF_DIGITS)
                    new_path = os.path.join(trg_path, new_name)
                    if ext == '.gif':
                        thum_dir = os.path.join(trg_path, '__thumbnail__')
                        if not os.path.exists(thum_dir):
                            os.mkdir(thum_dir)
                        self._gif_to_zip(file_path, new_path, thum_dir)
                        values_dict['Size'] += (os.path.getsize(new_path + '.zip') / (1024*1024))
                    else:
                        # TODO: 上書き操作は仮で禁止にしている
                        new_path = new_path + ext
                        if not os.path.exists(new_path):
                            if op_mode == 'move':
                                shutil.move(file_path, new_path)
                            elif op_mode == 'copy':
                                shutil.copyfile(file_path, new_path)
                        values_dict['Size'] += (os.path.getsize(new_path) / (1024*1024))
                    values_dict['FileNum'] += 1
                    self.file_op_progress['done_file'] += 1
                values_dict['Updated'] = datetime.datetime.now()

            elif op_mode == 'delete':

                # deleteの場合はindexのリストが渡されている想定
                # renameも兼ねるため、結局trg_path内を全探索する

                title_dir, file_list = self.get_file_list(title)
                
                new_favorite = []
                new_chapter = []
                count_new_idx = 0
                for i, fname in enumerate(file_list):

                    idx_str, ext = os.path.splitext(fname) # インデックスと拡張子に分解
                    idx = int(idx_str)

                    fpath = os.path.join(title_dir, fname)

                    if ext == '.zip':
                        thum_name = idx_str + '.png'
                        thum_path = os.path.join(title_dir, '__thumbnail__', thum_name)

                    if idx in src_list:
                        fsize = os.path.getsize(fpath) / (1024*1024)
                        os.remove(fpath)
                        if ext == '.zip':
                            os.remove(thum_path)
                        values_dict['FileNum'] -= 1
                        values_dict['Size'] -= fsize
                        self.file_op_progress['done_file'] += 1
                    else:
                        if idx != count_new_idx:
                            new_idx_str = str(count_new_idx).zfill(self.FILE_NUMBER_OF_DIGITS)
                            new_path = os.path.join(title_dir, new_idx_str + ext)
                            os.rename(fpath, new_path)
                            if ext == '.zip':
                                new_thum_path = os.path.join(title_dir, '__thumbnail__', new_idx_str + '.png')
                                os.rename(thum_path, new_thum_path)
                        if idx in ftask['init_favorite']:
                            new_favorite.append(count_new_idx)
                        if idx in ftask['init_chapter']:
                            new_chapter.append(count_new_idx)
                        count_new_idx += 1
                    
                values_dict['favorite'] = sorted(new_favorite)
                values_dict['chapter'] = sorted(new_chapter)

            # データベース情報更新
            self.update_record(title, values_dict=values_dict)
            self.logger.debug('Copy Operation Finished')

    def _delete_titles(self, titles):

        for title in titles:
            del_path = os.path.join(self.data_dir, title)
            if os.path.exists(del_path):
                shutil.rmtree(del_path)

        self.logger.debug('Delete Operation Finished')

    def file_op_is_alive(self):
        return self.file_op_thread.is_alive()

    def get_file_op_progress(self):
        return copy.deepcopy(self.file_op_progress)

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
        self.cursor.execute(sql)

        result = self.cursor.fetchall()

        if convert:
            if type(col_name) is list:
                tmp_dict = {}
                for cl in col_name:
                    tmp_dict[cl] = []
                for row in result:
                    for i, cl in enumerate(col_name):
                        tmp_dict[cl].append(self._convert_list(row[i]))
                return tmp_dict
            elif type(col_name) is str:
                tmp_list = []
                for row in result:
                    tmp_list += self._convert_list(row[0])
                return tmp_list
        else:
            return result

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

    def get_file_list(self, title):

        file_dir = os.path.join(self.data_dir, title)

        if not os.path.exists(file_dir):
            return '', []

        #登録時に拡張子はフィルタされるのでファイルすべてを取得しているが、早くなるかは不明
        #tmp_list = sorted(glob.glob(os.path.join(file_dir, "*")))
        #file_list = [os.path.basename(r) for r in tmp_list]

        tmp_list = self.search_files(file_dir)
        #tmp_list = sorted(list(chain.from_iterable([glob.glob(os.path.join(file_dir, "*." + ext)) for ext in self.SUPPORTED_EXT])))
        
        file_list = [os.path.basename(r) for r in tmp_list]

        return file_dir, file_list


    # 追加項目操作
    def get_additional_table(self):
        """
        ユーザ作成のタグ一覧の取得
        (= MainTable以外のテーブル名の一覧)
        """
        table_list = []
        self.cursor.execute("select * from sqlite_master where type='table'")
        for x in self.cursor.fetchall():
            if not x[1] == 'MainTable':
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

    def add_tag(self, table, values):
        """
        新規タグを追加する
            tagはMainTable内に存在するタグ種別名
            valuesは追加するタグ内容のリスト[Name, InitialCharacter]
        Nameが重複した場合はFalseリターン
        """
        if self.tag_is_exist(table, values[0]):
            return False

        try:
            if values[3] == '':
                tmp_tuple = (values[0], values[1], values[2], '')
            else:
                im_ext = self._asign_tag_image(table, values[3], values[0])
                tmp_tuple = (values[0], values[1], values[2], im_ext)

            sql = 'insert into {}(Name, InitialCharacter, Link, Image) VALUES(?,?,?,?)'.format(table)
            self.logger.debug('{} {}'.format(sql, tmp_tuple))
            self.cursor.execute(sql, tmp_tuple)
            self.connection.commit()

            return True
        except:
            return False

    def update_tag(self, table, tag_name, values_dict):
        """
        タグの情報を変更する。
        """
        if 'Name' in values_dict.keys():
            if self.tag_is_exist(table, values_dict['Name']):
                return False

        data_list = []

        for key, value in values_dict.items():

            if type(value) is list:
                tmp_val = LIST_DELIMITER.join([str(i) for i in value])
            else:
                tmp_val = value

            if key == 'Image':
                # valueが空欄の場合は削除指令
                
                im_path = self.get_tag_image(table,tag_name)
                try:
                    os.remove(im_path)
                except:
                    self.logger.debug('Failed to remove file. {}'.format(im_path))
                finally:
                    if value == '':
                        tmp_val = ''
                    else:
                        tmp_val = self._asign_tag_image(table, value, tag_name)

            data_list.append('{0}="{1}"'.format(key,tmp_val))

        sql_set_data = ','.join(data_list)
        sql = 'UPDATE {0} SET {1} WHERE Name="{2}"'.format(table, sql_set_data, tag_name)

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

            self._update_tag_image(table, old_name, new_name)

            sql = 'SELECT Title,{} FROM MainTable'.format(table)
            ret = self.cursor.execute(sql)

            for row in ret.fetchall():
                title = row[0]
                tag_list = self._convert_list(row[1])
                if old_name in tag_list:
                    new_list = [new_name if t == old_name else t for t in tag_list]
                    update_list.append((title,{table:copy.deepcopy(new_list)}))
            
            for ul in update_list:
                self.update_record(title=ul[0],values_dict=ul[1])

        return True

    def delete_tags(self, table, names):
        for name in names:
            sql = 'DELETE FROM {} WHERE Name="{}"'.format(table, name)

            im_path = self.get_tag_image(table, name)
            if im_path != '':
                try:
                    os.remove(im_path)
                except:
                    self.logger.debug('Failed to remove file. {}'.format(im_path))

            self.logger.debug(sql)
            self.cursor.execute(sql)

        self.connection.commit()
        return

    def tag_is_exist(self, table, name):
        sql = 'SELECT COUNT(*) FROM {} WHERE Name="{}"'.format(table, name)
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        return result[0][0] != 0

    def get_tag_image(self, table, name):
        sql = 'SELECT Image FROM {} WHERE Name="{}"'.format(table, name)
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        if result[0][0] == '':
            return ''
        else:
            im_name = '{}{}'.format(name, result[0][0])
            return os.path.join(self.tag_dir, table, im_name)


    def _asign_tag_image(self, table, src_path, tag_name):

        tmp_path = os.path.join(self.tag_dir, table)
        if not os.path.exists(tmp_path):
            os.mkdir(tmp_path)

        _, ext = os.path.splitext(src_path)
        new_name = '{}{}'.format(tag_name, ext)

        try:
            shutil.copyfile(src_path, os.path.join(tmp_path, new_name))
        except:
            self.logger.debug('Failed to copy file. {}'.format(src_path))

        return ext

    def _update_tag_image(self, table, old_name, new_name):

        sql = 'SELECT Image FROM {} WHERE Name="{}"'.format(table, new_name)
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        if result[0][0] == '':
            return

        ext = result[0][0]

        old_im_path = os.path.join(self.tag_dir, table, '{}{}'.format(old_name, ext))
        new_im_path = os.path.join(self.tag_dir, table, '{}{}'.format(new_name, ext))

        try:
            os.rename(old_im_path, new_im_path)
        except:
            self.logger.debug('Failed to change name. {} -> {}'.format(old_im_path, new_im_path))


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


    def tag_backup(self):
        
        date_str = datetime.datetime.now().strftime('%Y%m%d%H%M')
        save_dir = os.path.join(self.db_root, self.BACKUP_DIR, date_str)

        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        table_list = self.get_additional_table()
        for table in table_list:
            fname = os.path.join(save_dir, table + '.csv')
            with open(fname, "w", encoding=self.FILE_ENCODING) as write_file:
                sql = 'SELECT Name,InitialCharacter,IsFavorite,Link FROM {}'.format(table)
                for row in self.cursor.execute(sql):
                    write_txt = ','.join([str(r) for r in row])
                    write_file.write(write_txt)


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
        shutil.make_archive(dst_dir, 'zip', dst_dir)
        shutil.rmtree(dst_dir)

    def search_files(self, path):
        p = Path(path)
        file_list = sorted(list(chain.from_iterable([p.glob("*." + ext) for ext in self.SUPPORTED_EXT])))
        return [str(r) for r in file_list]