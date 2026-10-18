"""Text columns backed by GTK 4 list models and reusable list item factories."""

from gi.repository import GObject, Gtk, Pango


class TextRow(GObject.Object):
    def __init__(self, values):
        super().__init__()
        self.values = tuple(str(value) for value in values)


def text_column(title, index, *, expand=False, markup=False):
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item):
        item.set_child(Gtk.Label(
            xalign=0, margin_start=8, margin_end=8, margin_top=6,
            margin_bottom=6, ellipsize=Pango.EllipsizeMode.END,
        ))

    def bind(_factory, item):
        label = item.get_child()
        value = item.get_item().values[index]
        if markup:
            label.set_markup(value)
        else:
            label.set_text(value)
        label.set_tooltip_text(label.get_text())

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    column = Gtk.ColumnViewColumn.new(title, factory)
    column.set_expand(expand)
    column.set_resizable(True)
    return column
