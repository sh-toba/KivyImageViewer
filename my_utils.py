from pathlib import Path
import os, glob, re
from itertools import chain

def search_files(path, exts):
        p = Path(path)
        file_list = list(chain.from_iterable([p.glob("*." + ext) for ext in exts]))
        return sorted([str(r) for r in file_list], key=numericalSort)

def numericalSort(value):
    numbers = re.compile(r'(\d+)')
    parts = numbers.split(value)
    parts[1::2] = map(int, parts[1::2])
    return parts