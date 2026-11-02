"""Reusable widgets (their look is defined in edusense.kv)."""
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView


class Collapse(BoxLayout):
    """A box that takes no space (and ignores touches) while open is False."""

    open = BooleanProperty(True)


class Select(ButtonBehavior, BoxLayout):
    """Looks like a text field; tapping opens a bottom sheet to pick one value."""

    caption = StringProperty("")
    text = StringProperty("")
    placeholder = StringProperty("Select")
    values = ListProperty([])

    def __init__(self, **kw):
        self.register_event_type("on_pick")
        super().__init__(**kw)

    def on_pick(self, value):
        pass

    def on_release(self):
        if not self.values:
            return
        Sheet(title=self.caption or self.placeholder, options=list(self.values), selected=self.text, owner=self).open()

    def choose(self, value):
        changed = value != self.text
        self.text = value
        if changed:
            self.dispatch("on_pick", value)


class Sheet(ModalView):
    title = StringProperty("")
    options = ListProperty([])
    selected = StringProperty("")
    owner = ObjectProperty(None, allownone=True)
    max_h = NumericProperty(0)

    def on_pre_open(self, *_):
        self.max_h = Window.height * 0.7
        box = self.ids.rows
        box.clear_widgets()
        for value in self.options:
            row = Factory.OptionRow()
            row.text, row.picked = value, (value == self.selected)
            row.bind(on_release=lambda _r, v=value: self.pick(v))
            box.add_widget(row)

    def on_touch_down(self, touch):
        if not self.ids.panel.collide_point(*touch.pos):
            self.dismiss()  # tap on the dimmed area closes the sheet
            return True
        return super().on_touch_down(touch)

    def pick(self, value):
        self.dismiss()
        if self.owner is not None:
            self.owner.choose(value)


class Dialog(ModalView):
    title = StringProperty("")
    message = StringProperty("")
    hint = StringProperty("")
    with_field = BooleanProperty(False)
    password = BooleanProperty(False)
    ok_text = StringProperty("OK")
    danger = BooleanProperty(False)

    def __init__(self, on_ok=None, **kw):
        self._on_ok = on_ok
        super().__init__(**kw)

    def on_open(self, *_):
        if self.with_field:
            Clock.schedule_once(lambda _dt: setattr(self.ids.field, "focus", True), 0.25)

    def accept(self):
        text = self.ids.field.text
        self.dismiss()
        if self._on_ok:
            self._on_ok(text) if self.with_field else self._on_ok()


class Toast(Label):
    """Short message that fades out by itself."""

    bad = BooleanProperty(False)

    def show(self, text, bad=False, seconds=2.6):
        self.text, self.bad = text, bad
        Animation.cancel_all(self, "opacity")
        anim = Animation(opacity=1, d=0.15) + Animation(opacity=1, d=seconds) + Animation(opacity=0, d=0.3)
        anim.start(self)


def initials(name):
    parts = [p for p in (name or "").replace("-", " ").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
