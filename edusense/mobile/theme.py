"""Colours, dark/light mode and font scale. Bound in the .kv as app.th.<name>."""
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty
from kivy.utils import get_color_from_hex as hx

DARK = dict(
    bg="#0e1320", surface="#161d2e", surface2="#1f283b", border="#2b364d",
    text="#e9eef8", muted="#9aa8c0", accent="#4f8cff", accent_fg="#ffffff",
    ok="#3ecf8e", bad="#ff6b6b", warn="#f5b942",
)
LIGHT = dict(
    bg="#f2f5fa", surface="#ffffff", surface2="#eaeef5", border="#d9e0ec",
    text="#141b2a", muted="#586378", accent="#2f6fe4", accent_fg="#ffffff",
    ok="#168a5c", bad="#d23b3b", warn="#a96a0c",
)
STEPS = [0.85, 1.0, 1.15, 1.3, 1.5]


class Theme(EventDispatcher):
    dark = BooleanProperty(True)
    scale = NumericProperty(1.0)

    bg = ColorProperty(hx(DARK["bg"]))
    surface = ColorProperty(hx(DARK["surface"]))
    surface2 = ColorProperty(hx(DARK["surface2"]))
    border = ColorProperty(hx(DARK["border"]))
    text = ColorProperty(hx(DARK["text"]))
    muted = ColorProperty(hx(DARK["muted"]))
    accent = ColorProperty(hx(DARK["accent"]))
    accent_fg = ColorProperty(hx(DARK["accent_fg"]))
    ok = ColorProperty(hx(DARK["ok"]))
    bad = ColorProperty(hx(DARK["bad"]))
    warn = ColorProperty(hx(DARK["warn"]))

    def __init__(self, dark=True, scale=1.0, **kw):
        super().__init__(**kw)
        self.scale = scale if scale in STEPS else 1.0
        self.dark = bool(dark)
        self.apply()
        self.bind(dark=lambda *_: self.apply())

    def apply(self):
        for key, value in (DARK if self.dark else LIGHT).items():
            setattr(self, key, hx(value))

    def toggle(self):
        self.dark = not self.dark

    def bigger(self):
        self.scale = STEPS[min(STEPS.index(self.scale) + 1, len(STEPS) - 1)]

    def smaller(self):
        self.scale = STEPS[max(STEPS.index(self.scale) - 1, 0)]
