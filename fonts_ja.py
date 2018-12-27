from kivy.resources import resource_add_path
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.utils import platform

def add_paths(*paths):
    for p in reversed(paths):
        resource_add_path(p)

def set_regular(family, *filenames):
    for f in filenames:
        try:
            LabelBase.register(family, f)
            break
        except IOError:
            continue
    else:
        raise IOError('No appropriate fonts for Kivy UI')

_platform = platform

if _platform is 'android':
    add_paths('/system/fonts', '/data/fonts')
    set_regular(DEFAULT_FONT,
        'DroidSansJapanese.ttf',
        'MTLmr3m.ttf',
        'MTLc3m.ttf',
        'DroidSansFallback.ttf',
    )

elif _platform is 'ios':
    add_paths('/Library/Fonts')
    set_regular(DEFAULT_FONT,
        'Osaka.ttf',
        'OsakaMono.ttf',
    )

elif _platform is 'linux':
    add_paths('/usr/share/fonts/truetype/ipafont', '/usr/local/share/font-ipa')
    set_regular(DEFAULT_FONT,
        'ipagp.ttf', # IPAfont (http://ipafont.ipa.go.jp/)
        'ipagp.otf', # IPAfont (http://ipafont.ipa.go.jp/)
    )

elif _platform is 'macosx':
    add_paths('/Library/Fonts', '/System/Library/Fonts')
    set_regular(DEFAULT_FONT,
        'Hiragino Sans GB W3.otf',
        'Osaka.ttf',
        'OsakaMono.ttf',
        'AppleGothic.ttf',
    )

elif _platform is 'win':
    add_paths('c:/Windows/Fonts')
    set_regular(DEFAULT_FONT,
        'meiryo.ttc'
    )

else:
    raise IOError('Unknown platform: %s' % _platform)