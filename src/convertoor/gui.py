"""GTK 4 / libadwaita drag-and-drop interface."""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from . import engine  # noqa: E402
from . import formats as F  # noqa: E402
from .cli import expand  # noqa: E402

HOMEPAGE = "https://github.com/calebtrueman/convertoor"

CSS = """
.drop-hover {
  background-color: alpha(@accent_bg_color, 0.10);
  outline: 2px dashed @accent_color;
  outline-offset: -10px;
  border-radius: 12px;
}
.file-progress { min-width: 90px; }
.format-arrow { opacity: 0.55; }
"""


def _esc(text):
    return GLib.markup_escape_text(str(text), -1)


def _human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class Settings:
    def __init__(self):
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        self.path = os.path.join(base, "convertoor", "settings.json")
        try:
            with open(self.path) as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as fh:
                json.dump(self.data, fh, indent=2)
        except OSError:
            pass


def _open_folder_of(path):
    """Show ``path`` in the file manager, selecting it when possible."""
    uri = Gio.File.new_for_path(path).get_uri()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                      "org.freedesktop.FileManager1", "ShowItems",
                      GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, 3000,
                      None)
        return
    except GLib.Error:
        pass
    folder = Gio.File.new_for_path(os.path.dirname(path)).get_uri()
    try:
        Gio.AppInfo.launch_default_for_uri(folder, None)
    except GLib.Error:
        pass


class FileRow(Adw.ActionRow):
    PENDING, RUNNING, DONE, FAILED = range(4)

    def __init__(self, window, path):
        super().__init__()
        self.window = window
        self.path = path
        self.fmt = F.detect(path)
        self.targets = list(engine.targets(self.fmt)) if self.fmt else []
        self.state = self.PENDING
        self.job = None
        self.outputs = []
        self._last_fraction = -1

        self.set_title(_esc(os.path.basename(path)))
        try:
            size = _human_size(os.path.getsize(path))
        except OSError:
            size = ""
        if self.fmt:
            self.base_subtitle = f"{F.describe(self.fmt)} · {size}"
            icon = F.CATEGORY_ICONS[F.category(self.fmt)]
        else:
            self.base_subtitle = f"Unknown type · {size}"
            icon = "dialog-question-symbolic"
        self.add_prefix(Gtk.Image.new_from_icon_name(icon))

        box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.add_suffix(box)

        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, visible=False)
        self.progress.add_css_class("file-progress")
        box.append(self.progress)

        self.status_icon = Gtk.Image(visible=False)
        box.append(self.status_icon)

        self.open_btn = Gtk.Button(icon_name="folder-open-symbolic", visible=False,
                                   valign=Gtk.Align.CENTER, tooltip_text="Show in folder")
        self.open_btn.add_css_class("flat")
        self.open_btn.connect("clicked", self._on_open)
        box.append(self.open_btn)

        if self.targets:
            arrow = Gtk.Label(label="→")
            arrow.add_css_class("format-arrow")
            box.append(arrow)
            labels = [f"{F.label(t)}" for t in self.targets]
            self.dropdown = Gtk.DropDown.new_from_strings(labels)
            self.dropdown.set_valign(Gtk.Align.CENTER)
            self.dropdown.set_tooltip_text("Convert to")
            self.dropdown.connect("notify::selected", lambda *a: self._reset_if_done())
            box.append(self.dropdown)
            preferred = window.last_target_for(self.fmt)
            if preferred in self.targets:
                self.dropdown.set_selected(self.targets.index(preferred))
        else:
            self.dropdown = None
        missing = engine.missing_backends(self.fmt) if self.fmt else []
        names = " and ".join(b.name for b in missing)
        if missing:
            self.set_tooltip_text("Not installed — install: " +
                                  "; ".join(b.install_hint for b in missing))
        if not self.targets:
            self.base_subtitle += (f" · Requires {names} (not installed)" if missing
                                   else " · Unsupported file type")
        elif missing:
            self.base_subtitle += f" · More formats require {names}"

        remove = Gtk.Button(icon_name="window-close-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Remove")
        remove.add_css_class("flat")
        remove.connect("clicked", self._on_remove)
        box.append(remove)
        self._set_subtitle(self.base_subtitle)

    # -- helpers --
    def _set_subtitle(self, text):
        self.set_subtitle(_esc(text))

    @property
    def target(self):
        if not self.dropdown:
            return None
        idx = self.dropdown.get_selected()
        return self.targets[idx] if 0 <= idx < len(self.targets) else None

    def set_target(self, fmt):
        if self.dropdown and fmt in self.targets and self.state != self.RUNNING:
            self.dropdown.set_selected(self.targets.index(fmt))

    def convertible(self):
        return self.target is not None and self.state in (self.PENDING, self.FAILED)

    def _reset_if_done(self):
        if self.state in (self.DONE, self.FAILED):
            self.state = self.PENDING
            self.status_icon.set_visible(False)
            self.open_btn.set_visible(False)
            self._set_subtitle(self.base_subtitle)
        self.window.update_actions()

    # -- conversion lifecycle (called on the main thread) --
    def start(self):
        self.state = self.RUNNING
        self.status_icon.set_visible(False)
        self.open_btn.set_visible(False)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        if self.dropdown:
            self.dropdown.set_sensitive(False)
        self._set_subtitle(f"Converting to {F.label(self.target)}…")
        self._pulse_id = GLib.timeout_add(120, self._pulse)
        self._indeterminate = True

    def _pulse(self):
        if self.state != self.RUNNING:
            return False
        if self._indeterminate:
            self.progress.pulse()
        return True

    def on_progress(self, fraction):
        if self.state != self.RUNNING:
            return False
        if fraction is None:
            self._indeterminate = True
        else:
            self._indeterminate = False
            self.progress.set_fraction(fraction)
            self._set_subtitle(f"Converting to {F.label(self.target)}… {int(fraction * 100)}%")
        return False

    def finish(self, outputs, error):
        self.progress.set_visible(False)
        if self.dropdown:
            self.dropdown.set_sensitive(True)
        if error is None:
            self.state = self.DONE
            self.outputs = outputs
            self.status_icon.set_from_icon_name("object-select-symbolic")
            self.status_icon.set_tooltip_text("Converted")
            self.open_btn.set_visible(True)
            where = ""
            if os.path.dirname(outputs[0]) != os.path.dirname(self.path) and len(outputs) == 1:
                where = f" in {os.path.basename(os.path.dirname(outputs[0])) or '/'}"
            if len(outputs) == 1:
                self._set_subtitle(f"Saved as {os.path.basename(outputs[0])}{where}")
            else:
                self._set_subtitle(f"Saved {len(outputs)} files in "
                                   f"{os.path.basename(os.path.dirname(outputs[0]))}")
        elif isinstance(error, engine.Cancelled):
            self.state = self.PENDING
            self._set_subtitle(self.base_subtitle + " · Cancelled")
        else:
            self.state = self.FAILED
            self.status_icon.set_from_icon_name("dialog-error-symbolic")
            self.status_icon.set_tooltip_text(str(error))
            first = str(error).strip().splitlines()[0] if str(error).strip() else "Failed"
            self._set_subtitle(f"Error: {first}")
        self.status_icon.set_visible(self.state in (self.DONE, self.FAILED))
        self.job = None
        return False

    def _on_open(self, *_):
        if self.outputs:
            _open_folder_of(self.outputs[0])

    def _on_remove(self, *_):
        if self.job:
            self.job.cancel()
        self.window.remove_row(self)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Convertoor")
        self.set_default_size(820, 600)
        self.settings = Settings()
        self.rows = []
        self.pool = ThreadPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.running = 0
        self.batch_done = 0
        self.batch_failed = 0
        self._chooser = None
        self._bulk_updating = False
        self.output_dir = self.settings.get("output_dir")
        if self.output_dir and not os.path.isdir(self.output_dir):
            self.output_dir = None

        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):
            provider.load_from_string(CSS)
        else:
            try:
                provider.load_from_data(CSS.encode())
            except TypeError:
                provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)
        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add Files (Ctrl+O)")
        add_btn.connect("clicked", lambda *_: self.choose_files())
        header.pack_start(add_btn)
        self.clear_btn = Gtk.Button(icon_name="edit-clear-all-symbolic",
                                    tooltip_text="Clear List", sensitive=False)
        self.clear_btn.connect("clicked", lambda *_: self.clear())
        header.pack_start(self.clear_btn)

        menu = Gio.Menu()
        menu.append("Installed Converters", "app.tools")
        menu.append("Keyboard Shortcuts", "app.shortcuts")
        menu.append("About Convertoor", "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                  tooltip_text="Main Menu")
        header.pack_end(menu_btn)

        self._add_missing_banner(root)

        self.toasts = Adw.ToastOverlay(vexpand=True)
        root.append(self.toasts)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.toasts.set_child(self.stack)

        # Empty state
        status = Adw.StatusPage(
            icon_name=APP_ID,
            title="Drop Files Here",
            description="Images, audio, video, documents, spreadsheets, slides, ebooks, "
                        "archives, fonts and data files — or a whole folder.",
        )
        browse = Gtk.Button(label="Browse Files…", halign=Gtk.Align.CENTER)
        browse.add_css_class("pill")
        browse.add_css_class("suggested-action")
        browse.connect("clicked", lambda *_: self.choose_files())
        status.set_child(browse)
        self.stack.add_named(status, "empty")

        # File list
        scrolled = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=900, margin_top=18, margin_bottom=18,
                          margin_start=12, margin_end=12)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                   valign=Gtk.Align.START)
        self.listbox.add_css_class("boxed-list")
        clamp.set_child(self.listbox)
        scrolled.set_child(clamp)
        self.stack.add_named(scrolled, "list")

        # Bottom bar
        bar = Gtk.ActionBar()
        root.append(bar)
        self.bar = bar
        bulk_box = Gtk.Box(spacing=8)
        bulk_box.append(Gtk.Label(label="Convert all to"))
        self.bulk_model = Gtk.StringList()
        self.bulk_formats = []
        self.bulk = Gtk.DropDown(model=self.bulk_model, sensitive=False)
        self.bulk.connect("notify::selected", self._on_bulk_changed)
        bulk_box.append(self.bulk)
        bar.pack_start(bulk_box)

        self.convert_btn = Gtk.Button(label="Convert", sensitive=False)
        self.convert_btn.add_css_class("suggested-action")
        self.convert_btn.connect("clicked", self._on_convert_clicked)
        bar.pack_end(self.convert_btn)

        out_menu = Gio.Menu()
        out_menu.append("Same Folder as Original", "win.output-same")
        out_menu.append("Choose Folder…", "win.output-choose")
        self.out_btn = Gtk.MenuButton(menu_model=out_menu)
        out_content = Gtk.Box(spacing=6)
        out_content.append(Gtk.Image.new_from_icon_name("folder-symbolic"))
        self.out_label = Gtk.Label(ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=22)
        out_content.append(self.out_label)
        self.out_btn.set_child(out_content)
        bar.pack_end(self.out_btn)
        for name, cb in (("output-same", lambda *_: self.set_output_dir(None)),
                         ("output-choose", lambda *_: self.choose_output_dir())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
        self._update_out_label()
        self.connect("close-request", self._on_close)

        # Drag and drop
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        drop.connect("enter", self._on_drop_enter)
        drop.connect("leave", self._on_drop_leave)
        self.toasts.add_controller(drop)

        self.update_actions()

    def _add_missing_banner(self, root):
        """Tell the user up front when LibreOffice/Calibre aren't installed."""
        missing = [b for b in engine.BACKENDS
                   if isinstance(b, engine.HostBackend) and not b.available()]
        key = ",".join(b.name for b in missing)
        if not missing or self.settings.get("banner_dismissed") == key:
            return
        text = " and ".join(f"{b.name} is required for {b.short_required}" for b in missing)
        text = text[0].upper() + text[1:] + " — not installed."
        if not hasattr(Adw, "Banner"):  # libadwaita < 1.3
            GLib.idle_add(lambda: self.toasts.add_toast(Adw.Toast(title=text, timeout=8))
                          and False)
            return
        banner = Adw.Banner(title=text, button_label="Details", revealed=True)

        def details(*_):
            banner.set_revealed(False)
            self.settings.set("banner_dismissed", key)
            ToolsWindow(self).present()

        banner.connect("button-clicked", details)
        root.append(banner)

    # -- settings helpers --
    def last_target_for(self, fmt):
        return self.settings.get("last_targets", {}).get(fmt)

    def _remember_target(self, fmt, target):
        last = dict(self.settings.get("last_targets", {}))
        last[fmt] = target
        self.settings.set("last_targets", last)

    def set_output_dir(self, path):
        self.output_dir = path
        self.settings.set("output_dir", path)
        self._update_out_label()

    def _on_close(self, *_):
        for row in self.rows:
            if row.job:
                row.job.cancel()
        self.pool.shutdown(wait=False)
        return False

    def _update_out_label(self):
        if self.output_dir:
            self.out_label.set_label(os.path.basename(self.output_dir.rstrip("/")) or "/")
            self.out_btn.set_tooltip_text(f"Saving to {self.output_dir}")
        else:
            self.out_label.set_label("Same folder")
            self.out_btn.set_tooltip_text("Converted files are saved next to the originals")

    # -- drag and drop --
    def _on_drop_enter(self, *_):
        self.toasts.add_css_class("drop-hover")
        return Gdk.DragAction.COPY

    def _on_drop_leave(self, *_):
        self.toasts.remove_css_class("drop-hover")

    def _on_drop(self, _target, value, _x, _y):
        self.toasts.remove_css_class("drop-hover")
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        self.add_files(paths)
        return bool(paths)

    # -- file management --
    def add_files(self, paths):
        known = {r.path for r in self.rows}
        added = 0
        for path in expand([engine.host_path(p) for p in paths]):
            path = os.path.abspath(path)
            if path in known or not os.path.isfile(path):
                continue
            known.add(path)
            row = FileRow(self, path)
            self.rows.append(row)
            self.listbox.append(row)
            added += 1
        if added:
            self.stack.set_visible_child_name("list")
        self._rebuild_bulk()
        self.update_actions()

    def remove_row(self, row):
        if row in self.rows:
            self.rows.remove(row)
            self.listbox.remove(row)
        if not self.rows:
            self.stack.set_visible_child_name("empty")
        self._rebuild_bulk()
        self.update_actions()

    def clear(self):
        for row in list(self.rows):
            if row.job:
                row.job.cancel()
            self.listbox.remove(row)
        self.rows = []
        self.stack.set_visible_child_name("empty")
        self._rebuild_bulk()
        self.update_actions()

    def _rebuild_bulk(self):
        counts = {}
        order = []
        for row in self.rows:
            for t in row.targets:
                if t not in counts:
                    order.append(t)
                counts[t] = counts.get(t, 0) + 1
        convertible = sum(1 for r in self.rows if r.targets)
        # Formats every file supports first, then the rest.
        order.sort(key=lambda t: -counts[t] if counts[t] == convertible else 0)
        self._bulk_updating = True
        self.bulk_formats = [None] + order
        labels = ["Each file’s choice"] + [
            F.label(t) if counts[t] == convertible else f"{F.label(t)} ({counts[t]} files)"
            for t in order]
        self.bulk_model.splice(0, self.bulk_model.get_n_items(), labels)
        self.bulk.set_selected(0)
        self.bulk.set_sensitive(bool(order))
        self._bulk_updating = False

    def _on_bulk_changed(self, *_):
        if self._bulk_updating:
            return
        idx = self.bulk.get_selected()
        if 0 < idx < len(self.bulk_formats):
            fmt = self.bulk_formats[idx]
            for row in self.rows:
                row.set_target(fmt)

    def update_actions(self):
        self.clear_btn.set_sensitive(bool(self.rows))
        if self.running:
            self.convert_btn.set_label("Cancel")
            self.convert_btn.remove_css_class("suggested-action")
            self.convert_btn.add_css_class("destructive-action")
            self.convert_btn.set_sensitive(True)
        else:
            n = sum(1 for r in self.rows if r.convertible())
            self.convert_btn.set_label(f"Convert {n} File{'s' if n != 1 else ''}" if n else
                                       "Convert")
            self.convert_btn.remove_css_class("destructive-action")
            self.convert_btn.add_css_class("suggested-action")
            self.convert_btn.set_sensitive(n > 0)

    # -- conversion --
    def _on_convert_clicked(self, *_):
        if self.running:
            for row in self.rows:
                if row.job:
                    row.job.cancel()
            return
        self.convert_all()

    def convert_all(self):
        rows = [r for r in self.rows if r.convertible()]
        if not rows:
            return
        self.batch_done = self.batch_failed = 0
        for row in rows:
            self._remember_target(row.fmt, row.target)
            self._start_row(row)
        self.update_actions()

    def _start_row(self, row):
        target = row.target

        def progress(fraction):
            # Throttle UI updates to whole percentages.
            if fraction is not None:
                pct = int(fraction * 100)
                if pct == row._last_fraction:
                    return
                row._last_fraction = pct
            GLib.idle_add(row.on_progress, fraction)

        job = engine.Job(progress)
        row.job = job
        row._last_fraction = -1
        row.start()
        self.running += 1
        out_dir = self.output_dir
        if not out_dir and not os.access(os.path.dirname(row.path), os.W_OK):
            # Read-only location (or a sandboxed drop we can't write next to).
            out_dir = (GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
                       or os.path.expanduser("~"))

        def work():
            try:
                outputs = [str(p) for p in engine.convert_file(row.path, target, out_dir, job)]
                GLib.idle_add(self._row_finished, row, outputs, None)
            except Exception as exc:  # report every failure on the row
                GLib.idle_add(self._row_finished, row, [], exc)

        self.pool.submit(work)

    def _row_finished(self, row, outputs, error):
        row.finish(outputs, error)
        self.running -= 1
        if error is None:
            self.batch_done += 1
        elif not isinstance(error, engine.Cancelled):
            self.batch_failed += 1
        if self.running == 0:
            self._batch_complete()
        self.update_actions()
        return False

    def _batch_complete(self):
        done, failed = self.batch_done, self.batch_failed
        if not done and not failed:
            return
        if failed:
            msg = f"{done} converted, {failed} failed"
        else:
            msg = f"Converted {done} file{'s' if done != 1 else ''}"
        toast = Adw.Toast(title=msg, timeout=4)
        self.toasts.add_toast(toast)
        app = self.get_application()
        if app and not self.is_active():
            note = Gio.Notification.new("Conversion finished")
            note.set_body(msg)
            app.send_notification("finished", note)
        if app and getattr(app, "self_test", None):
            app.self_test_finished(self)

    # -- dialogs --
    def choose_files(self):
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog(title="Add Files", modal=True)

            def done(dlg, result):
                try:
                    files = dlg.open_multiple_finish(result)
                except GLib.Error:
                    return
                self.add_files([files.get_item(i).get_path() for i in range(files.get_n_items())
                                if files.get_item(i).get_path()])

            dialog.open_multiple(self, None, done)
            return
        chooser = Gtk.FileChooserNative(title="Add Files", transient_for=self,
                                        action=Gtk.FileChooserAction.OPEN,
                                        accept_label="_Add", modal=True)
        chooser.set_select_multiple(True)

        def response(dlg, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                files = dlg.get_files()
                self.add_files([files.get_item(i).get_path() for i in range(files.get_n_items())
                                if files.get_item(i).get_path()])
            self._chooser = None

        chooser.connect("response", response)
        self._chooser = chooser
        chooser.show()

    def choose_output_dir(self):
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog(title="Save Converted Files To", modal=True,
                                    accept_label="Select")
            if self.output_dir:
                dialog.set_initial_folder(Gio.File.new_for_path(self.output_dir))

            def done(dlg, result):
                try:
                    folder = dlg.select_folder_finish(result)
                except GLib.Error:
                    return
                if folder and folder.get_path():
                    self.set_output_dir(folder.get_path())

            dialog.select_folder(self, None, done)
            return
        chooser = Gtk.FileChooserNative(title="Save Converted Files To", transient_for=self,
                                        action=Gtk.FileChooserAction.SELECT_FOLDER,
                                        accept_label="_Select", modal=True)

        def response(dlg, resp):
            if resp == Gtk.ResponseType.ACCEPT and dlg.get_file():
                self.set_output_dir(dlg.get_file().get_path())
            self._chooser = None

        chooser.connect("response", response)
        self._chooser = chooser
        chooser.show()


class ToolsWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True, title="Installed Converters")
        self.set_default_size(560, 620)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(box)
        box.append(Adw.HeaderBar())
        scrolled = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(scrolled)
        clamp = Adw.Clamp(margin_top=18, margin_bottom=18, margin_start=12, margin_end=12)
        scrolled.set_child(clamp)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        clamp.set_child(inner)
        intro = Gtk.Label(wrap=True, xalign=0, label=(
            "Convertoor converts files with these open-source tools. Formats handled by a "
            "tool marked ⚠ won't work until that tool is installed. Install it with your "
            "package manager, then restart Convertoor."
            + ("\n\nIn the Flatpak, LibreOffice and Calibre aren't bundled: install them on "
               "your system or from Flathub and Convertoor will use them."
               if engine.IN_FLATPAK else "")))
        intro.add_css_class("dim-label")
        inner.append(intro)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        inner.append(lb)
        for b in engine.BACKENDS:
            path = b.path()
            row = Adw.ActionRow(title=_esc(b.name))
            if path:
                where = "Built in" if not b.binaries else path
                row.set_subtitle(_esc(f"{b.description}\n{where}"))
                icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
            else:
                needed = f"\nRequired for {b.required_for}." if b.required_for else ""
                row.set_subtitle(_esc(f"{b.description}{needed}\n"
                                      f"Not installed — install: {b.install_hint}"))
                icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            row.add_suffix(icon)
            lb.append(row)


class ConvertoorApp(Adw.Application):
    def __init__(self, self_test=None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.self_test = self_test
        self.exit_code = 0
        if self_test:
            # Don't hand the test off to an already-running instance.
            self.set_flags(self.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        for name, cb, accels in (
            ("about", self._on_about, None),
            ("tools", self._on_tools, None),
            ("shortcuts", self._on_shortcuts, ["<Control>question"]),
            ("quit", lambda *_: self.quit(), ["<Control>q"]),
            ("open", lambda *_: self._window().choose_files(), ["<Control>o"]),
            ("convert", lambda *_: self._window().convert_all(), ["<Control>Return"]),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

    def _window(self):
        win = self.props.active_window
        if win is None:
            win = MainWindow(self)
        return win

    def do_activate(self):
        win = self._window()
        win.present()
        if self.self_test:
            GLib.timeout_add(500, self._run_self_test, win)

    def do_open(self, files, n_files, hint):
        win = self._window()
        win.present()
        win.add_files([f.get_path() for f in files if f.get_path()])

    # -- self test (used in CI to exercise the real GUI end to end) --
    def _run_self_test(self, win):
        path, fmt = self.self_test
        win.add_files([path])
        if not win.rows:
            print("SELF-TEST: file was not added", file=sys.stderr)
            self.exit_code = 1
            self.quit()
            return False
        idx = win.bulk_formats.index(fmt) if fmt in win.bulk_formats else -1
        if idx < 0:
            print(f"SELF-TEST: {fmt} not offered; got {win.bulk_formats}", file=sys.stderr)
            self.exit_code = 1
            self.quit()
            return False
        win.bulk.set_selected(idx)
        win.convert_all()
        GLib.timeout_add_seconds(180, self._self_test_timeout)
        return False

    def self_test_finished(self, win):
        row = win.rows[0]
        if row.state == FileRow.DONE and all(os.path.exists(p) for p in row.outputs):
            print("SELF-TEST OK:", ", ".join(row.outputs))
            self.exit_code = 0
        else:
            print(f"SELF-TEST FAILED: {row.get_subtitle()}", file=sys.stderr)
            self.exit_code = 1
        GLib.timeout_add(300, lambda: self.quit() or False)

    def _self_test_timeout(self):
        print("SELF-TEST: timed out", file=sys.stderr)
        self.exit_code = 1
        self.quit()
        return False

    # -- actions --
    def _on_tools(self, *_):
        ToolsWindow(self._window()).present()

    def _on_shortcuts(self, *_):
        builder = Gtk.Builder.new_from_string(SHORTCUTS_UI, -1)
        win = builder.get_object("shortcuts")
        win.set_transient_for(self._window())
        win.present()

    def _on_about(self, *_):
        parent = self._window()
        if hasattr(Adw, "AboutWindow"):
            about = Adw.AboutWindow(
                transient_for=parent, application_name="Convertoor", application_icon=APP_ID,
                version=__version__, developer_name="Caleb Trueman", website=HOMEPAGE,
                issue_url=HOMEPAGE + "/issues", license_type=Gtk.License.MIT_X11,
                comments="Drag-and-drop converter for images, audio, video, documents "
                         "and more.",
            )
        else:
            about = Gtk.AboutDialog(
                transient_for=parent, modal=True, program_name="Convertoor", logo_icon_name=APP_ID,
                version=__version__, website=HOMEPAGE, license_type=Gtk.License.MIT_X11,
                authors=["Caleb Trueman"],
                comments="Drag-and-drop converter for images, audio, video, documents "
                         "and more.",
            )
        about.present()


SHORTCUTS_UI = """
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts">
    <property name="modal">1</property>
    <child>
      <object class="GtkShortcutsSection">
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title">General</property>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Add files</property>
              <property name="accelerator">&lt;Control&gt;o</property></object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Convert</property>
              <property name="accelerator">&lt;Control&gt;Return</property></object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Keyboard shortcuts</property>
              <property name="accelerator">&lt;Control&gt;question</property></object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Quit</property>
              <property name="accelerator">&lt;Control&gt;q</property></object></child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""


def run_gui(files=None, self_test=None):
    if self_test:
        self_test = (os.path.abspath(self_test[0]), F.canonical(self_test[1]) or self_test[1])
    app = ConvertoorApp(self_test)
    # Files go through GApplication so a running instance receives them.
    status = app.run([sys.argv[0]] + [os.path.abspath(f) for f in (files or [])])
    return app.exit_code if self_test else status
