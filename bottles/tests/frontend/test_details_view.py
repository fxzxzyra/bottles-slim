"""Navigation pages retain content until hidden and can reopen their sections."""

from types import SimpleNamespace

from gi.repository import Adw, Gtk

from bottles.backend.models.config import BottleConfig
from bottles.frontend.views.details import DetailsView
from bottles.frontend.views.eagle import EagleView


def test_hidden_navigation_page_unloads_the_stack_after_leaving(iterate_until):
    window = Adw.Window()
    navigation = Adw.NavigationView()
    window.set_content(navigation)
    home = Adw.NavigationPage.new(Gtk.Box(), "Home")
    stack = Gtk.Stack()
    stack.add_named(Adw.Bin(), "preferences")
    stack.add_named(Adw.Bin(), "dependencies")
    details = Adw.NavigationPage.new(stack, "Details")
    navigation.add(home)
    navigation.add(details)
    view = SimpleNamespace(stack_bottle=stack, _page_generation=0)
    details.connect("hidden", lambda *_args: DetailsView.unload_view(view))
    window.present()
    try:
        navigation.push(details)
        iterate_until(lambda: details.get_mapped())
        assert stack.get_first_child() is not None
        navigation.pop()
        iterate_until(lambda: stack.get_first_child() is None)
        assert navigation.get_visible_page() is home
        assert view._unloading is False
    finally:
        window.destroy()


def test_section_navigation_opens_once_and_returns_to_overview():
    navigation = Adw.NavigationView()
    overview = Adw.NavigationPage.new(Gtk.Box(), "Overview")
    section = Adw.NavigationPage.new(Gtk.Box(), "Settings")
    navigation.add(overview)
    navigation.add(section)
    view = SimpleNamespace(section_navigation=navigation, section_page=section)
    DetailsView.open_section(view)
    DetailsView.open_section(view)
    assert navigation.get_visible_page() is section
    DetailsView.go_back_sidebar(view)
    assert navigation.get_visible_page() is overview


def test_unload_view_empties_the_page_stack():
    stack = Gtk.Stack()
    stack.add_named(Adw.Bin(), "preferences")
    stack.add_named(Adw.Bin(), "dependencies")
    DetailsView.unload_view(SimpleNamespace(stack_bottle=stack, _page_generation=0))
    assert stack.get_first_child() is None


def test_built_details_template_navigates_and_discards_stale_population(monkeypatch, iterate_until):
    from gi.repository import GLib
    from bottles.frontend.views import details as module

    # Content pages have their own suites. Keep their actual GTK parent/child
    # behavior while isolating the navigation container from Wine and catalogs.
    class ContentPage(Adw.Bin):
        def __init__(self, *_args):
            super().__init__()
            self.actions = Gtk.Box()

    for name in ("BottleView", "InstallersView", "DependenciesView", "RegistryRulesView",
                 "PreferencesView", "VersioningView", "TaskManagerView", "EagleView"):
        monkeypatch.setattr(module, name, ContentPage)
    parent = Adw.Window()
    parent.manager = SimpleNamespace(versioning_manager=object())
    parent.details_page = Adw.NavigationPage(title="Details")
    parent.toggle_selection_mode = lambda _enabled: None
    view = module.DetailsView(parent)
    parent.details_page.set_child(view)
    parent.set_content(parent.details_page)
    parent.present()
    try:
        iterate_until(lambda: view.stack_bottle.get_child_by_name("preferences") is not None)
        assert view.default_view.get_first_child() is view.view_bottle
        view.stack_bottle.set_visible_child_name("preferences")
        view.open_section()
        assert view.section_navigation.get_visible_page() is view.section_page
        assert view.content_title.get_title() == "Settings"
        view.go_back_sidebar()
        assert view.section_navigation.get_visible_page() is view.overview_page
        view.build_pages()
        view.unload_view()
        done = []
        GLib.idle_add(lambda: done.append(True))
        iterate_until(lambda: bool(done))
        assert view.stack_bottle.get_first_child() is None
    finally:
        parent.destroy()


def test_eagle_follows_the_selected_bottle():
    eagle = EagleView(SimpleNamespace(), BottleConfig())
    previous_manager = eagle.manager
    unused = SimpleNamespace(set_config=lambda **kwargs: None, update=lambda **kwargs: None)
    view = SimpleNamespace(
        view_bottle=unused,
        view_preferences=unused,
        view_taskmanager=unused,
        view_installers=unused,
        view_registry_rules=unused,
        view_versioning=unused,
        view_eagle=eagle,
    )
    for config in (
        BottleConfig(Name="First", Runner="soda-11.0-34"),
        BottleConfig(Name="Second", Environment="Application", Runner="system-wine"),
    ):
        DetailsView.set_config(view, config, rebuild_pages=False)
        assert eagle.config is config
        assert eagle.manager.config is config
        assert eagle.manager is not previous_manager
        previous_manager = eagle.manager
