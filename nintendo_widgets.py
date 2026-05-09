"""Nintendo-style widgets: rounded tiles, hero cards, pill buttons, price ticker.

Visual language is inspired by the Switch home screen / Mario UI:
- Cream background, vibrant primary tile colors
- Soft drop shadows, rounded corners
- Tap-bounce animation (scale 1.0 -> 0.92 -> 1.04 -> 1.0)
- Chunky display font for headers and numbers
"""

from kivy.animation import Animation
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.metrics import dp
from kivy.properties import (ColorProperty, ListProperty, NumericProperty,
                             StringProperty, ObjectProperty)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget


# --- Palette ---------------------------------------------------------------
SWITCH_RED = (0.902, 0.0, 0.071, 1)        # #E60012
SWITCH_BLUE = (0.0, 0.690, 0.882, 1)       # #00B0E1
MARIO_YELLOW = (0.984, 0.816, 0.0, 1)      # #FBD000
LUIGI_GREEN = (0.102, 0.612, 0.271, 1)     # #1A9C45
STAR_PURPLE = (0.608, 0.424, 0.949, 1)     # #9B6CF2
CREAM = (1.0, 0.973, 0.906, 1)             # #FFF8E7
NAVY = (0.055, 0.133, 0.251, 1)            # #0E2240
WHITE = (1, 1, 1, 1)
SHADOW = (0, 0, 0, 0.18)


def _bounce_press(widget):
    """Scale-down on press."""
    Animation.cancel_all(widget, 'press_scale')
    a = Animation(press_scale=0.93, d=0.06, t='out_quad')
    a.start(widget)


def _bounce_release(widget):
    """Pop back on release with overshoot."""
    Animation.cancel_all(widget, 'press_scale')
    a = Animation(press_scale=1.04, d=0.08, t='out_back') + \
        Animation(press_scale=1.0, d=0.08, t='out_quad')
    a.start(widget)


class TileButton(ButtonBehavior, BoxLayout):
    """Big square tile with emoji icon + label. Used on home screen."""
    bg_color = ColorProperty(SWITCH_BLUE)
    icon = StringProperty("[?]")
    label = StringProperty("")
    press_scale = NumericProperty(1.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = [dp(14)] * 4
        self.spacing = dp(8)

        with self.canvas.before:
            self._shadow_color = Color(*SHADOW)
            self._shadow = RoundedRectangle(radius=[dp(22)])
            self._fill_color = Color(*self.bg_color)
            self._fill = RoundedRectangle(radius=[dp(22)])

        self._icon_label = Label(
            text=self.icon, font_size=dp(56), halign="center", valign="middle")
        self._text_label = Label(
            text=self.label, font_size=dp(20), bold=True, halign="center",
            valign="middle", color=WHITE)
        self._text_label.size_hint_y = None
        self._text_label.height = dp(28)

        self.add_widget(self._icon_label)
        self.add_widget(self._text_label)

        self.bind(pos=self._redraw, size=self._redraw,
                  bg_color=self._update_color, icon=self._update_icon,
                  label=self._update_label, press_scale=self._redraw)

    def _redraw(self, *args):
        s = self.press_scale
        w, h = self.size[0] * s, self.size[1] * s
        x = self.pos[0] + (self.size[0] - w) / 2
        y = self.pos[1] + (self.size[1] - h) / 2
        self._shadow.pos = (x, y - dp(4))
        self._shadow.size = (w, h)
        self._fill.pos = (x, y)
        self._fill.size = (w, h)

    def _update_color(self, *args):
        self._fill_color.rgba = self.bg_color

    def _update_icon(self, *args):
        self._icon_label.text = self.icon

    def _update_label(self, *args):
        self._text_label.text = self.label

    def on_press(self):
        _bounce_press(self)

    def on_release(self):
        _bounce_release(self)


class HeroCard(BoxLayout):
    """White rounded panel with a soft drop shadow."""
    radius = NumericProperty(dp(18))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*SHADOW)
            self._shadow = RoundedRectangle(radius=[self.radius])
            Color(*WHITE)
            self._fill = RoundedRectangle(radius=[self.radius])
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *args):
        self._shadow.pos = (self.pos[0], self.pos[1] - dp(4))
        self._shadow.size = self.size
        self._fill.pos = self.pos
        self._fill.size = self.size


class PillButton(ButtonBehavior, Label):
    """Rounded pill button used for clarifying-question answers."""
    bg_color = ColorProperty(SWITCH_BLUE)
    press_scale = NumericProperty(1.0)
    radius = NumericProperty(dp(28))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = kwargs.get('font_size', dp(18))
        self.bold = True
        self.color = WHITE
        self.padding_x = dp(20)
        self.padding_y = dp(12)
        with self.canvas.before:
            self._shadow_color = Color(*SHADOW)
            self._shadow = RoundedRectangle(radius=[self.radius])
            self._fill_color = Color(*self.bg_color)
            self._fill = RoundedRectangle(radius=[self.radius])
        self.bind(pos=self._redraw, size=self._redraw,
                  bg_color=self._update_color, press_scale=self._redraw)

    def _redraw(self, *args):
        s = self.press_scale
        w, h = self.size[0] * s, self.size[1] * s
        x = self.pos[0] + (self.size[0] - w) / 2
        y = self.pos[1] + (self.size[1] - h) / 2
        self._shadow.pos = (x, y - dp(3))
        self._shadow.size = (w, h)
        self._fill.pos = (x, y)
        self._fill.size = (w, h)

    def _update_color(self, *args):
        self._fill_color.rgba = self.bg_color

    def on_press(self):
        _bounce_press(self)

    def on_release(self):
        _bounce_release(self)


class PriceTicker(Label):
    """Big chunky cost-range display."""
    low = NumericProperty(0)
    high = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_size = dp(38)
        self.bold = True
        self.color = NAVY
        self.halign = "center"
        self.valign = "middle"
        self.bind(low=self._update, high=self._update, size=self._update_size)

    def _update_size(self, *args):
        self.text_size = self.size

    def _update(self, *args):
        if self.high > 0:
            self.text = f"${int(self.low):,} – ${int(self.high):,}"
        else:
            self.text = ""


class StyledTextInput(BoxLayout):
    """TextInput wrapped in a HeroCard-style rounded white box."""
    text = StringProperty("")
    hint = StringProperty("")
    multiline = ObjectProperty(False)
    on_submit = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.padding = [dp(14), dp(10)]
        with self.canvas.before:
            Color(*SHADOW)
            self._shadow = RoundedRectangle(radius=[dp(14)])
            Color(*WHITE)
            self._fill = RoundedRectangle(radius=[dp(14)])
        from kivy.uix.textinput import TextInput
        self._input = TextInput(
            text=self.text, hint_text=self.hint, multiline=self.multiline,
            background_color=(0, 0, 0, 0), foreground_color=NAVY,
            cursor_color=NAVY, font_size=dp(20), padding=[0, dp(8), 0, 0])
        self._input.bind(text=self._on_text)
        self.add_widget(self._input)
        self.bind(pos=self._redraw, size=self._redraw, text=self._sync_in)

    def _redraw(self, *args):
        self._shadow.pos = (self.pos[0], self.pos[1] - dp(3))
        self._shadow.size = self.size
        self._fill.pos = self.pos
        self._fill.size = self.size

    def _on_text(self, _input, value):
        if self.text != value:
            self.text = value

    def _sync_in(self, _self, value):
        if self._input.text != value:
            self._input.text = value
