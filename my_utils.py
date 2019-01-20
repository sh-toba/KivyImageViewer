from pathlib import Path
import os, glob, re
from itertools import chain

def search_files(path, exts):
        p = Path(path)
        file_list = list(chain.from_iterable([p.glob("*." + ext) for ext in exts]))

        ret_list = []
        file_size = 0
        for path_obj in file_list:
                ret_list.append(str(path_obj))
                file_size += path_obj.stat().st_size

        return sorted(ret_list, key=numericalSort), file_size

def search_files_deep(path, exts):
        p = Path(path)
        file_list = list(chain.from_iterable([p.glob("**/*." + ext) for ext in exts]))

        ret_list = []
        file_size = 0
        for path_obj in file_list:
                if path_obj.is_file():
                        ret_list.append(str(path_obj))
                        file_size += path_obj.stat().st_size

        return sorted(ret_list, key=numericalSort), file_size
                        

def numericalSort(value):
        numbers = re.compile(r'(\d+)')
        parts = numbers.split(value)
        parts[1::2] = map(int, parts[1::2])
        return parts
