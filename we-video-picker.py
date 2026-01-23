#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GLib, Gdk, GdkPixbuf, Pango
import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote, unquote

# ================= CONFIG =================
WE_WORKSHOP_DEFAULT = str(Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/steamapps/workshop/content/431960")
COMMON_WP_INSTALLS = [
    Path.home() / ".steam/steam/steamapps/common/wallpaper_engine",
    Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/steamapps/common/wallpaper_engine",
]
CONFIG_FILE = "plasma-org.kde.plasma.desktop-appletsrc"
CONFIG_GROUP_PREFIX = "Wallpaper-luisbocanegra-smart-video-wallpaper-reborn"
KEY_NAME = "VideoUrls"
# ===========================================

class AnimatedGifImage(Gtk.Picture):
    """Custom widget that animates GIF files using GdkPixbuf animation iterator"""
    
    def __init__(self, gif_path, width, height):
        super().__init__()
        self.set_content_fit(Gtk.ContentFit.COVER)
        self.set_size_request(width, height)
        
        try:
            self.animation = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
            self.iter = self.animation.get_iter(None)
            
            # Set initial frame
            pixbuf = self.iter.get_pixbuf()
            if pixbuf:
                scaled = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
                self.set_pixbuf(scaled)
            
            # Start animation timer
            self.width = width
            self.height = height
            self.timeout_id = GLib.timeout_add(50, self._update_frame)
            
        except Exception as e:
            print(f"Error loading GIF animation: {e}")
    
    def _update_frame(self):
        try:
            # Advance to next frame
            self.iter.advance(None)
            pixbuf = self.iter.get_pixbuf()
            
            if pixbuf:
                scaled = pixbuf.scale_simple(self.width, self.height, GdkPixbuf.InterpType.BILINEAR)
                self.set_pixbuf(scaled)
            
            return True  # Continue animation
        except Exception:
            return False  # Stop animation on error
    
    def cleanup(self):
        """Stop animation timer"""
        if hasattr(self, 'timeout_id') and self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

class WallpaperPicker(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.example.WEVideoPicker")
        self.connect("activate", self.on_activate)
        self.animated_widgets = []  # Track animated widgets for cleanup

    def load_state(self):
        try:
            if hasattr(self, "state_file") and self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_state(self, state: dict):
        try:
            if hasattr(self, "state_file"):
                existing = {}
                try:
                    if self.state_file.exists():
                        with open(self.state_file, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                except Exception:
                    existing = {}
                existing.update(state or {})
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(existing, f)
        except Exception:
            pass

    def on_activate(self, app):
        win = Gtk.ApplicationWindow(application=app, title="Wallpaper Engine Video Picker")
        win.set_default_size(1320, 900)
        try:
            self.main_window = win
        except Exception:
            pass

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        win.set_child(vbox)

        # Path entry row (separate row under the header)
        hbox_entry = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.entry_path = Gtk.Entry()

        initial = None
        for p in COMMON_WP_INSTALLS:
            try:
                if p.exists():
                    initial = str(p)
                    break
            except Exception:
                continue
        if not initial:
            initial = WE_WORKSHOP_DEFAULT

        try:
            cfg_dir = Path(GLib.get_user_config_dir()) if GLib.get_user_config_dir() else Path.home() / ".config"
        except Exception:
            cfg_dir = Path.home() / ".config"
        try:
            cfg_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.state_file = cfg_dir / "we-video-picker.json"

        state = self.load_state()
        last = state.get("last_path") if isinstance(state, dict) else None
        if last:
            initial = last

        self.entry_path.set_text(initial)
        self.entry_path.set_hexpand(True)
        self.entry_path.set_placeholder_text("Path to Wallpaper Engine install (..../steamapps/common/wallpaper_engine)")
        # Top-left status area (selected title above status/link)
        try:
            self.lbl_selected_title = Gtk.Label()
            self.lbl_selected_title.set_wrap(True)
            self.lbl_selected_title.set_wrap_mode(Pango.WrapMode.WORD)
            self.lbl_selected_title.set_ellipsize(Pango.EllipsizeMode.END)
            self.lbl_selected_title.set_text("")

            self.lbl_status = Gtk.Label(label="Ready – enter path and click Import")
            self.lbl_status.set_margin_top(8)
            self.lbl_status.set_margin_bottom(8)
            try:
                self.lbl_status.set_use_markup(True)
                self.lbl_status.set_track_visited_links(True)
                self.lbl_status.connect("activate-link", self.on_status_activate_link)
            except Exception:
                pass
            try:
                self.lbl_status.set_halign(Gtk.Align.START)
            except Exception:
                pass
            try:
                # xalign controls text justification inside the label (0.0 = left)
                self.lbl_status.set_xalign(0.0)
            except Exception:
                pass

            status_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            status_top.append(self.lbl_selected_title)
            status_top.append(self.lbl_status)
            status_top.set_halign(Gtk.Align.START)
        except Exception:
            pass

        hbox_entry.append(self.entry_path)

        btn_import = Gtk.Button(label="Import Wallpapers")
        btn_import.add_css_class("suggested-action")
        btn_import.connect("clicked", self.on_import_clicked)

        # Header: title/status on left, controls on the right (Sort, Import, Help)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_valign(Gtk.Align.START)
        header.set_hexpand(True)

        status_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_top.append(self.lbl_selected_title)
        status_top.append(self.lbl_status)
        status_top.set_halign(Gtk.Align.START)
        header.append(status_top)

        # spacer pushes controls to the right of the header
        try:
            header_spacer = Gtk.Box()
            header_spacer.set_hexpand(True)
            header.append(header_spacer)
        except Exception:
            pass

        # Controls box aligned with the title
        try:
            controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            controls.set_valign(Gtk.Align.START)
            lbl_sort = Gtk.Label(label="Sort:")
            lbl_sort.set_margin_top(6)
            controls.append(lbl_sort)
            self.sort_combo = Gtk.ComboBoxText()
            for opt in ("A-Z", "Z-A", "Size on Disk", "Subscription Date"):
                self.sort_combo.append_text(opt)
            self.sort_combo.set_active(0)
            self.sort_combo.set_tooltip_text("Sort wallpapers")
            self.sort_combo.connect("changed", self.on_sort_changed)
            controls.append(self.sort_combo)
            controls.append(btn_import)

            # help button
            help_btn = Gtk.Button()
            try:
                img = Gtk.Image.new_from_icon_name("preferences-system-symbolic")
                img.set_valign(Gtk.Align.CENTER)
                img.set_halign(Gtk.Align.CENTER)
                help_btn.set_child(img)
            except Exception:
                help_btn.set_label("Help")
            help_btn.set_tooltip_text("Help / Settings")
            help_btn.connect("clicked", self.on_help_clicked)
            controls.append(help_btn)

            header.append(controls)
        except Exception:
            pass

        # checkbox placed on the entry row
        chk_startup = Gtk.CheckButton(label="Import on startup")
        try:
            chk_active = False
            if isinstance(state, dict):
                chk_active = bool(state.get("import_on_startup", False))
        except Exception:
            chk_active = False
        try:
            chk_startup.set_active(chk_active)
        except Exception:
            pass

        # keep a reference so settings window can sync this checkbox
        try:
            self.chk_startup = chk_startup
        except Exception:
            pass

        def on_chk_toggled(chk):
            try:
                self.save_state({"import_on_startup": bool(chk.get_active())})
            except Exception:
                pass

        chk_startup.connect("toggled", on_chk_toggled)
        hbox_entry.append(chk_startup)

        # append header first (top) then entry row below it
        vbox.append(header)
        vbox.append(hbox_entry)

        # Status area (secondary) — keeps small messages
        self.status_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.append(self.status_area)

        # Sorting dropdown moved to top row

        # Auto-trigger import on startup
        try:
            try:
                chk_active = chk_startup.get_active()
            except Exception:
                chk_active = False

            if chk_active and hasattr(self, "state_file") and self.state_file.exists():
                GLib.idle_add(self.on_import_clicked, btn_import)
        except Exception:
            pass

        # Compatible wallpapers section
        try:
            self.compat_expander = Gtk.Expander(label="Compatible Wallpapers")
            self.compat_expander.set_expanded(True)
        except Exception:
            self.compat_expander = Gtk.Expander()

        try:
            lbl_compat = Gtk.Label()
            lbl_compat.set_use_markup(True)
            lbl_compat.set_markup("<span weight='bold' size='12000'>Compatible Wallpapers</span>")
            self.compat_expander.set_label_widget(lbl_compat)
        except Exception:
            pass

        self.compat_grid = Gtk.Grid()
        self.compat_grid.set_row_spacing(16)
        self.compat_grid.set_column_spacing(16)
        self.compat_grid.set_margin_top(12)
        self.compat_grid.set_margin_bottom(12)
        try:
            self.compat_grid.set_halign(Gtk.Align.CENTER)
            self.compat_grid.set_hexpand(False)
        except Exception:
            pass
        try:
            self.compat_grid.get_style_context().add_class("grid-bg")
        except Exception:
            pass
        try:
            self.compat_expander.set_child(self.compat_grid)
        except Exception:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(self.compat_grid)
            self.compat_expander.set_child(box)

        # Incompatible wallpapers section
        try:
            self.incompat_expander = Gtk.Expander(label="Incompatible Wallpapers (scene projects)")
            self.incompat_expander.set_expanded(False)
        except Exception:
            self.incompat_expander = Gtk.Expander()

        try:
            lbl_incompat = Gtk.Label()
            lbl_incompat.set_use_markup(True)
            lbl_incompat.set_markup("<span weight='bold' size='12000'>Incompatible Wallpapers (scene projects)</span>")
            self.incompat_expander.set_label_widget(lbl_incompat)
        except Exception:
            pass
        try:
            self.incompat_expander.connect("notify::expanded", self.on_incompat_expander_toggled)
        except Exception:
            pass

        self.incompat_grid = Gtk.Grid()
        self.incompat_grid.set_row_spacing(12)
        self.incompat_grid.set_column_spacing(12)
        self.incompat_grid.set_margin_top(12)
        self.incompat_grid.set_margin_bottom(12)
        try:
            self.incompat_grid.set_halign(Gtk.Align.CENTER)
            self.incompat_grid.set_hexpand(False)
        except Exception:
            pass
        try:
            self.incompat_grid.get_style_context().add_class("incompat-grid-bg")
        except Exception:
            pass
        try:
            self.incompat_expander.set_child(self.incompat_grid)
        except Exception:
            box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box2.append(self.incompat_grid)
            self.incompat_expander.set_child(box2)

        self.sections_scrolled = Gtk.ScrolledWindow()
        self.sections_scrolled.set_vexpand(True)
        self.sections_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.sections_box.append(self.compat_expander)
        self.sections_box.append(self.incompat_expander)
        self.sections_scrolled.set_child(self.sections_box)
        vbox.append(self.sections_scrolled)

        # CSS styling
        try:
            css = b"""
            .grid-bg {
                background-color: #2c2c2c;
                border-radius: 6px;
                padding: 8px;
            }
            .incompat-grid-bg {
                background-color: #5a0000;
                border-radius: 6px;
                padding: 8px;
            }
            """
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_display(win.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass

        self.clipboard = win.get_display().get_clipboard()

        win.present()

    def on_import_clicked(self, button):
        raw = self.entry_path.get_text().strip()
        if not raw:
            self.lbl_status.set_text("Please provide a path to Wallpaper Engine or the workshop content folder")
            return

        try:
            p = Path(raw).expanduser().resolve()
        except Exception:
            p = Path(raw)

        workshop_dir = None

        if (p / "project.json").exists() or p.name == "431960" or (p / "../431960").exists():
            for a in [p] + list(p.parents):
                if a.name == "431960":
                    workshop_dir = a
                    break
            if not workshop_dir:
                if p.is_dir() and any(x.is_dir() for x in p.iterdir()):
                    workshop_dir = p

        if not workshop_dir:
            steamapps = None
            for a in [p] + list(p.parents):
                if a.name == "steamapps":
                    steamapps = a
                    break
            if steamapps:
                candidate = steamapps / "workshop" / "content" / "431960"
                if candidate.exists():
                    workshop_dir = candidate

        if not workshop_dir and p.exists() and p.is_dir():
            try:
                found = False
                for child in p.iterdir():
                    if (child / "project.json").exists():
                        found = True
                        break
                if found:
                    workshop_dir = p
            except Exception:
                pass

        if not workshop_dir or not workshop_dir.exists():
            self.lbl_status.set_text("Could not locate workshop content folder from provided path")
            return

        path = str(workshop_dir)
        try:
            self.save_state({"last_path": path})
        except Exception:
            pass
        try:
            self.last_workshop_dir = path
            self.incompat_loaded = False
        except Exception:
            pass
        try:
            # hide the main address bar once a working path is set
            try:
                self.entry_path.set_visible(False)
            except Exception:
                pass
            try:
                if hasattr(self, "chk_startup"):
                    try:
                        self.chk_startup.set_visible(False)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
        self.lbl_status.set_text("Scanning... (this may take a while)")
        button.set_sensitive(False)

        threading.Thread(target=self.scan_wallpapers, args=(path, button), daemon=True).start()

    def scan_wallpapers(self, base_path, button):
        GLib.idle_add(self.clear_grid)
        GLib.idle_add(self.clear_incompatible_grid)

        items = []
        try:
            for item_id in os.listdir(base_path):
                item_dir = os.path.join(base_path, item_id)
                if not os.path.isdir(item_dir):
                    continue

                json_path = os.path.join(item_dir, "project.json")
                if not os.path.isfile(json_path):
                    continue

                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    proj_type = data.get("type", "").lower()

                    if proj_type == "scene":
                        continue

                    if proj_type not in ("video", "mp4", "webm"):
                        continue

                    file_rel = data.get("file") or data.get("preview")
                    if not file_rel:
                        continue

                    video_path = os.path.join(item_dir, file_rel)
                    if not os.path.isfile(video_path) or not video_path.lower().endswith((".mp4", ".webm", ".mkv")):
                        for cand in ("background.mp4", "background.webm", "project.mp4"):
                            vp = os.path.join(item_dir, cand)
                            if os.path.isfile(vp):
                                video_path = vp
                                break
                        else:
                            continue

                    title = data.get("title", item_id)
                    preview_static = None
                    for name in ("preview.jpg", "preview.png"):
                        pth = os.path.join(item_dir, name)
                        if os.path.isfile(pth):
                            preview_static = pth
                            break
                    preview_gif = None
                    gif_path = os.path.join(item_dir, "preview.gif")
                    if os.path.isfile(gif_path):
                        preview_gif = gif_path

                    try:
                        size = os.path.getsize(video_path)
                    except Exception:
                        size = 0
                    try:
                        sub_date = os.path.getmtime(item_dir)
                    except Exception:
                        sub_date = 0

                    items.append({
                        "title": title,
                        "video": video_path,
                        "preview": preview_static,
                        "preview_gif": preview_gif,
                        "id": item_id,
                        "dir": item_dir,
                        "size": size,
                        "sub_date": sub_date,
                    })
                except Exception:
                    continue

            GLib.idle_add(self.show_items, items)
            GLib.idle_add(self.lbl_status.set_text, f"Found {len(items)} compatible wallpapers.")
        except Exception as e:
            GLib.idle_add(self.lbl_status.set_text, f"Error: {str(e)}")
        finally:
            GLib.idle_add(button.set_sensitive, True)

    def clear_grid(self):
        # Clean up animated widgets before clearing
        for widget in self.animated_widgets:
            try:
                widget.cleanup()
            except Exception:
                pass
        self.animated_widgets.clear()
        
        while child := self.compat_grid.get_first_child():
            self.compat_grid.remove(child)

    def make_preview_widget(self, preview_static, preview_gif, width, height):
        # Prioritize GIF animation if available
        if preview_gif and os.path.isfile(preview_gif):
            try:
                animated = AnimatedGifImage(preview_gif, width, height)
                self.animated_widgets.append(animated)
                return animated
            except Exception as e:
                print(f"Failed to create animated GIF: {e}")

        # Fallback to static preview
        if preview_static and os.path.isfile(preview_static):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(preview_static, width, height, True)
                pic = Gtk.Picture.new_for_pixbuf(pixbuf)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(width, height)
                return pic
            except Exception as e:
                print(f"Failed to load static preview: {e}")

        # Empty placeholder
        pic = Gtk.Picture()
        pic.set_size_request(width, height)
        return pic

    def show_items(self, items):
        try:
            self.items_list = items
        except Exception:
            pass

        try:
            self.clear_grid()
        except Exception:
            pass

        for it in items:
            if "size" not in it:
                try:
                    it["size"] = os.path.getsize(it.get("video", "")) if it.get("video") else 0
                except Exception:
                    it["size"] = 0
            if "sub_date" not in it:
                try:
                    it["sub_date"] = Path(it.get("video", "")).parent.stat().st_mtime
                except Exception:
                    it["sub_date"] = 0

        sort_mode = getattr(self, "current_sort", None)
        try:
            if not sort_mode and hasattr(self, "sort_combo"):
                sort_mode = self.sort_combo.get_active_text()
        except Exception:
            sort_mode = sort_mode or "A-Z"

        if sort_mode == "A-Z":
            items = sorted(items, key=lambda x: x.get("title", "").lower())
        elif sort_mode == "Z-A":
            items = sorted(items, key=lambda x: x.get("title", "").lower(), reverse=True)
        elif sort_mode == "Size on Disk":
            items = sorted(items, key=lambda x: x.get("size", 0), reverse=True)
        elif sort_mode == "Subscription Date":
            items = sorted(items, key=lambda x: x.get("sub_date", 0), reverse=True)

        cols = 5
        CARD_WIDTH = 180
        CARD_HEIGHT = 180
        IMG_HEIGHT = (CARD_HEIGHT * 2) // 3
        LABEL_HEIGHT = CARD_HEIGHT - IMG_HEIGHT
        
        for i, item in enumerate(items):
            frame = Gtk.Frame()
            frame.add_css_class("card")

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            vbox.set_margin_top(8)
            vbox.set_margin_bottom(8)
            vbox.set_margin_start(8)
            vbox.set_margin_end(8)
            try:
                vbox.set_size_request(CARD_WIDTH, CARD_HEIGHT)
            except Exception:
                pass

            preview_static = item.get("preview")
            preview_gif = item.get("preview_gif")
            img_widget = self.make_preview_widget(preview_static, preview_gif, CARD_WIDTH, IMG_HEIGHT)
            vbox.append(img_widget)

            lbl = Gtk.Label(label=item["title"])
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(25)
            lbl.set_size_request(CARD_WIDTH, LABEL_HEIGHT)
            vbox.append(lbl)

            btn = Gtk.Button()
            btn.set_child(vbox)
            btn.item_data = item
            btn.connect("clicked", self.on_wallpaper_clicked)
            frame.set_child(btn)

            row = i // cols
            col = i % cols
            self.compat_grid.attach(frame, col, row, 1, 1)

    def clear_incompatible_grid(self):
        while child := self.incompat_grid.get_first_child():
            self.incompat_grid.remove(child)

    def on_sort_changed(self, combo):
        try:
            text = combo.get_active_text()
            if text:
                self.current_sort = text
                if hasattr(self, "items_list"):
                    GLib.idle_add(self.show_items, self.items_list)
        except Exception:
            pass

    def show_incompatible_items(self, items):
        cols = 5
        CARD_WIDTH = 180
        CARD_HEIGHT = 180
        IMG_HEIGHT = (CARD_HEIGHT * 2) // 3
        LABEL_HEIGHT = CARD_HEIGHT - IMG_HEIGHT
        
        for i, item in enumerate(items):
            frame = Gtk.Frame()
            try:
                frame.get_style_context().add_class("incompatible-frame")
            except Exception:
                pass

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            vbox.set_margin_top(8)
            vbox.set_margin_bottom(8)
            vbox.set_margin_start(8)
            vbox.set_margin_end(8)
            try:
                vbox.set_size_request(CARD_WIDTH, CARD_HEIGHT)
            except Exception:
                pass

            preview_static = item.get("preview")
            preview_gif = item.get("preview_gif")
            img = self.make_preview_widget(preview_static, preview_gif, CARD_WIDTH, IMG_HEIGHT)
            vbox.append(img)

            lbl = Gtk.Label(label=item.get("title", ""))
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(25)
            lbl.set_size_request(CARD_WIDTH, LABEL_HEIGHT)
            try:
                lbl.get_style_context().add_class("incompatible-title")
            except Exception:
                pass
            vbox.append(lbl)

            btn = Gtk.Button()
            btn.set_child(vbox)
            try:
                btn.set_sensitive(False)
                btn.set_tooltip_text("Not compatible: scene project")
            except Exception:
                pass
            frame.set_child(btn)

            row = i // cols
            col = i % cols
            self.incompat_grid.attach(frame, col, row, 1, 1)

    def scan_incompatible(self, base_path):
        GLib.idle_add(self.clear_incompatible_grid)
        items = []
        try:
            for item_id in os.listdir(base_path):
                item_dir = os.path.join(base_path, item_id)
                if not os.path.isdir(item_dir):
                    continue

                json_path = os.path.join(item_dir, "project.json")
                if not os.path.isfile(json_path):
                    continue

                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    proj_type = data.get("type", "").lower()
                    if proj_type != "scene":
                        continue

                    title = data.get("title", item_id)
                    preview_static = None
                    for name in ("preview.jpg", "preview.png"):
                        pth = os.path.join(item_dir, name)
                        if os.path.isfile(pth):
                            preview_static = pth
                            break
                    preview_gif = None
                    gif_path = os.path.join(item_dir, "preview.gif")
                    if os.path.isfile(gif_path):
                        preview_gif = gif_path

                    items.append({
                        "title": title,
                        "preview": preview_static,
                        "preview_gif": preview_gif,
                        "id": item_id,
                        "dir": item_dir,
                    })
                except Exception:
                    continue

            GLib.idle_add(self.show_incompatible_items, items)
            GLib.idle_add(self.lbl_status.set_text, f"Found {len(items)} incompatible wallpapers")
        except Exception as e:
            GLib.idle_add(self.lbl_status.set_text, f"Error scanning incompatible items: {e}")

    def on_wallpaper_clicked(self, button):
        item = button.item_data
        video_path = item["video"]

        if not Path(video_path).is_file():
            self.lbl_status.set_text(f"Video file not found: {video_path}")
            return

        uri = "file://" + quote(video_path)

        try:
            esc_title = GLib.markup_escape_text(item.get("title", "Selected"))
            self.lbl_selected_title.set_markup(
                f"<span weight='bold' size='17000'>{esc_title}</span>"
            )
        except Exception:
            self.lbl_selected_title.set_text(item.get("title", "Selected"))

        short_path = video_path.replace(str(Path.home()), "~")
        self.lbl_status.set_text(f"Applying: {short_path} …")

        try:
            self.clipboard.set(uri)
        except Exception:
            pass

        success = False
        try:
            possible_containments = ["1", "2", "11", "12", "21", "22"]

            plugin_id = "luisbocanegra.smart.video.wallpaper.reborn"

            for cont_id in possible_containments:
                group = f"Containments,{cont_id},Wallpaper,{plugin_id},General"

                result = subprocess.run(
                    [
                        "kwriteconfig6",
                        "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                        "--group", group,
                        "--key", "VideoUrls",
                        uri
                    ],
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    success = True
                    subprocess.run(
                        ["kwriteconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                         "--group", group, "--key", "RandomOrder", "false"],
                        capture_output=True
                    )
                    subprocess.run(
                        ["kwriteconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                         "--group", group, "--key", "PlaybackMode", "Single"],
                        capture_output=True
                    )
                    break

            if not success:
                raise RuntimeError("None of the common containment IDs worked")

        except Exception as e:
            self.lbl_status.set_text(f"Config update failed: {e}\nPath still copied to clipboard.")
            return

        try:
            js_script = f"""
            var uri = "{uri.replace('"', '\\"')}";
            var desktops = desktops();
            for (var i = 0; i < desktops.length; i++) {{
                var d = desktops[i];
                if (d.wallpaperPlugin === "luisbocanegra.smart.video.wallpaper.reborn") {{
                    d.currentConfigGroup = ["Wallpaper", "luisbocanegra.smart.video.wallpaper.reborn", "General"];
                    d.writeConfig("VideoUrls", uri);
                    d.writeConfig("LastVideo", uri);
                    d.reloadConfig();
                }}
            }}
            """

            subprocess.run(
                [
                    "qdbus", "org.kde.plasmashell", "/PlasmaShell",
                    "org.kde.PlasmaShell.evaluateScript", js_script
                ],
                check=True,
                timeout=8,
                capture_output=True
            )
            folder = Path(video_path).parent
            folder_uri = "file://" + quote(str(folder))
            self.lbl_status.set_markup(
                f"<a href='{folder_uri}'>Open in Explorer</a>"
            )

        except Exception as dbus_err:
            self.lbl_status.set_text("DBus reload failed → restarting Plasma shell…")
            try:
                subprocess.run(["plasmashell", "--replace"], 
                               start_new_session=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            except Exception:
                self.lbl_status.set_text("Reload failed. Try log out/in or manual plasmashell --replace")
    
    def on_status_activate_link(self, label, uri):
        try:
            if uri.startswith("file://"):
                local = uri[len("file://"):]
                try:
                    local = unquote(local)
                except Exception:
                    pass
                p = Path(local)
                if p.is_file():
                    target = str(p.parent)
                else:
                    target = str(p)

                try:
                    subprocess.run(["xdg-open", target], check=False)
                    return True
                except Exception:
                    try:
                        Gio.AppInfo.launch_default_for_uri("file://" + quote(target, safe="/:"), None)
                        return True
                    except Exception:
                        return False

            try:
                Gio.AppInfo.launch_default_for_uri(uri, None)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def on_incompat_expander_toggled(self, expander, pspec):
        try:
            if expander.get_expanded():
                if getattr(self, "incompat_loaded", False):
                    return
                base = getattr(self, "last_workshop_dir", None)
                if not base:
                    GLib.idle_add(self.lbl_status.set_text, "Please import wallpapers first to scan incompatible items")
                    return
                self.incompat_loaded = True
                threading.Thread(target=self.scan_incompatible, args=(base,), daemon=True).start()
        except Exception:
            pass

    def on_help_clicked(self, button):
        try:
            win = Gtk.Window(transient_for=getattr(self, "main_window", None))
            try:
                win.set_modal(True)
            except Exception:
                pass
            win.set_title("Settings / Help")
            help_text = """
1. Right Click Desktop and Select "Desktop & Wallpaper"
2. Click "Get New Plugins..." button 
3. Install "Smart Video Wallpaper Reborn"
4. Open Steam and Download "Wallpaper Engine"
5. Go to Steam Library
6. Right click "Wallpaper Engine"
7. Select Manage > Browse Local Files
8. Copy the file path from address bar
9. Paste it here and click "Import Wallpapers"
"""
            lbl = Gtk.Label()
            lbl.set_text(help_text)
            lbl.set_wrap(True)
            lbl.set_justify(Gtk.Justification.LEFT)
            lbl.set_margin_top(12)
            lbl.set_margin_bottom(12)
            lbl.set_margin_start(12)
            lbl.set_margin_end(12)

            # Title for help instructions
            title_lbl = Gtk.Label()
            try:
                title_lbl.set_markup("<span weight='bold' size='17000'>How to Find Wallpaper Engine Install Path</span>")
            except Exception:
                title_lbl.set_text("How to Find Wallpaper Engine Install Path")
            title_lbl.set_margin_bottom(2)
            title_lbl.set_margin_top(6)

            # Settings area: duplicate path entry and import-on-startup checkbox
            settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            settings_box.set_margin_start(12)
            settings_box.set_margin_end(12)

            # Path entry copy
            try:
                settings_entry = Gtk.Entry()
                try:
                    settings_entry.set_text(self.entry_path.get_text())
                except Exception:
                    settings_entry.set_text("")
                settings_entry.set_hexpand(True)
            except Exception:
                settings_entry = None

            # Apply button to copy path back to main entry and save
            def on_apply_clicked(btn):
                try:
                    if settings_entry:
                        newpath = settings_entry.get_text().strip()
                        if newpath:
                            try:
                                self.entry_path.set_text(newpath)
                                try:
                                    # ensure the main address bar is visible when user applies a new path
                                    self.entry_path.set_visible(True)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            try:
                                self.save_state({"last_path": newpath})
                            except Exception:
                                pass
                except Exception:
                    pass

            hbox_entry = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            if settings_entry:
                hbox_entry.append(settings_entry)
            apply_btn = Gtk.Button(label="Apply")
            apply_btn.connect("clicked", on_apply_clicked)
            hbox_entry.append(apply_btn)

            # Import on startup checkbox (mirror current state)
            try:
                settings_chk = Gtk.CheckButton(label="Import on startup")
                cur = False
                try:
                    if hasattr(self, "chk_startup"):
                        cur = bool(self.chk_startup.get_active())
                except Exception:
                    cur = False
                try:
                    settings_chk.set_active(cur)
                except Exception:
                    pass

                def on_settings_chk_toggled(chk):
                    try:
                        val = bool(chk.get_active())
                        try:
                            if hasattr(self, "chk_startup"):
                                self.chk_startup.set_active(val)
                        except Exception:
                            pass
                        try:
                            self.save_state({"import_on_startup": val})
                        except Exception:
                            pass
                    except Exception:
                        pass

                settings_chk.connect("toggled", on_settings_chk_toggled)
            except Exception:
                settings_chk = None

            # Assemble settings box: title above numbered list
            settings_box.append(title_lbl)
            settings_box.append(lbl)
            settings_box.append(hbox_entry)
            if settings_chk:
                settings_box.append(settings_chk)

            win.set_child(settings_box)
            win.set_default_size(590, 220)
            win.present()
        except Exception:
            pass

def main():
    app = WallpaperPicker()
    app.run()

if __name__ == "__main__":
    main()