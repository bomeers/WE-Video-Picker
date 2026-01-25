#!/usr/bin/env python3                                                        
#  _ _ _ _____    _____ _   _            _____ _     _           
# | | | |   __|  |  |  |_|_| |___ ___   |  _  |_|___| |_ ___ ___ 
# | | | |   __|  |  |  | | . | -_| . |  |   __| |  _| '_| -_|  _|
# |_____|_____|   \___/|_|___|___|___|  |__|  |_|___|_,_|___|_|  
# --------------------------------------------------------------
# Open Source Middleman Software to connect Wallpaper Engine to KDE Plugin "Smart Video Wallpaper Reborn"
# Author: Bo Meers
# Github: https://github.com/bomeers/WE-Video-Picker
#
# Full Disclosure: This software was made with the assistance of AI, but has been reviewed and modified by the author to make the UI/UX perfect.
# It Edits the ~/.config/plasma-org.kde.plasma.desktop-appletsrc file to set video wallpapers using the KDE plugin.
# It also Creates ~/.config/we-video-picker.json to store user preferences.
#
# Use at your own risk. Always back up your configuration files before using such tools.
# --------------------------------------------------------------
                                                               
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GLib, GdkPixbuf, Pango
import cairo
import math
import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote, unquote
from datetime import datetime
import shutil
import hashlib

# ================= CONFIG =================
WE_WORKSHOP_DEFAULT = str(Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/steamapps/workshop/content/431960")
COMMON_WP_INSTALLS = [
    Path.home() / ".steam/steam/steamapps/common/wallpaper_engine",
    Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/steamapps/common/wallpaper_engine",
]
# ===========================================

# Check the if KDE plugin "Smart Video Wallpaper Reborn" is installed
def is_kde_plugin_installed(plugin_id: str) -> bool:
    plugin_dir_name = plugin_id.replace(".", "-")
    
    base_locations = [
        Path.home() / ".local/share/plasma/wallpapers",
        Path.home() / ".local/share/kpackage/wallpapers",
        Path("/usr/share/plasma/wallpapers"),
        Path("/usr/share/kpackage/wallpapers"),
        Path("/usr/local/share/plasma/wallpapers"),
        Path("/usr/local/share/kpackage/wallpapers"),
    ]
    
    for base_dir in base_locations:
        # Check for exact directory name match
        exact_path = base_dir / plugin_dir_name
        if exact_path.exists() and exact_path.is_dir():
            return True
        
        alt_path = base_dir / plugin_id
        if alt_path.exists() and alt_path.is_dir():
            return True
        
        # Check if the base directory exists and search for any matching subdirectory
        if base_dir.exists() and base_dir.is_dir():
            try:
                for item in base_dir.iterdir():
                    if item.is_dir():
                        # Check if any subdirectory name contains the plugin identifier
                        item_name = item.name.lower()
                        if "luisbocanegra" in item_name and "smart" in item_name and "video" in item_name and "wallpaper" in item_name:
                            return True
            except Exception:
                continue
    
    return False

# TODO: Check if wallpaper engine is installed and if not, show error message box in the grid at the top.

def get_current_video_wallpaper_data():
    try:
        config_path = Path.home() / ".config/plasma-org.kde.plasma.desktop-appletsrc"
        if not config_path.exists():
            return {}
        
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        # Parse the config file to find VideoUrls entries
        current_group = None
        for line in config_content.split("\n"):
            line = line.strip()
            
            # Track current group
            if line.startswith("["):
                current_group = line
            
            # Look for VideoUrls in wallpaper engine files
            if "VideoUrls=" in line and current_group and "luisbocanegra" in current_group.lower():
                # Extract the video URL
                video_url = line.split("VideoUrls=", 1)[1].strip()
                
                # Convert file:// URL to path
                if video_url.startswith("file://"):
                    video_path = unquote(video_url[7:])  # Remove 'file://' and decode URL encoding
                    video_path = Path(video_path)
                    
                    if video_path.is_file():
                        # Get parent directory (project folder)
                        project_dir = video_path.parent
                        
                        # Look for project.json to get title
                        title = None
                        project_json = project_dir / "project.json"
                        if project_json.exists():
                            try:
                                with open(project_json, "r", encoding="utf-8") as pf:
                                    proj_data = json.load(pf)
                                    title = proj_data.get("title", "Untitled")
                            except Exception:
                                title = project_dir.name
                        else:
                            title = project_dir.name
                        
                        # Look for preview files
                        preview_static = None
                        preview_gif = None
                        
                        for name in ("preview.jpg", "preview.png"):
                            preview_path = project_dir / name
                            if preview_path.exists():
                                preview_static = str(preview_path)
                                break
                        
                        for name in ("preview.gif", "preview.webp"):
                            preview_path = project_dir / name
                            if preview_path.exists():
                                preview_gif = str(preview_path)
                                break
                        
                        return {
                            "title": title,
                            "preview": preview_static,
                            "preview_gif": preview_gif,
                            "video": str(video_path)
                        }
        
        return {}
    except Exception as e:
        print(f"Error reading current video wallpaper data: {e}")
        return {}

class AnimatedGifImage(Gtk.Picture):

    def __init__(self, gif_path, width, height, autoplay=False, hover=True):
        super().__init__()
        self.set_content_fit(Gtk.ContentFit.COVER)
        self.set_size_request(width, height)

        try:
            self.animation = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
            self.iter = self.animation.get_iter(None)

            # Set initial (static) first frame
            pixbuf = self.iter.get_pixbuf()
            if pixbuf:
                scaled = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
                self.set_pixbuf(scaled)

            # Store animation parameters
            self.width = width
            self.height = height
            self.timeout_id = None
            self.is_animating = False
            self.hover_control = bool(hover)

            # Connect hover events only if hover control is enabled
            if self.hover_control:
                motion_controller = Gtk.EventControllerMotion.new()
                motion_controller.connect("enter", self._on_hover_enter)
                motion_controller.connect("leave", self._on_hover_leave)
                self.add_controller(motion_controller)

            # Autoplay if requested
            if autoplay:
                try:
                    self.start_animation()
                except Exception:
                    pass

        except Exception as e:
            print(f"Error loading GIF animation: {e}")
    
    def _on_hover_enter(self, controller, x, y):
        """Start animation when mouse enters"""
        if not self.hover_control:
            return
        if not self.is_animating:
            self.is_animating = True
            self.timeout_id = GLib.timeout_add(50, self._update_frame)
    
    def _on_hover_leave(self, controller):
        """Stop animation when mouse leaves"""
        if not self.hover_control:
            return
        self.is_animating = False
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
        try:
            self.iter = self.animation.get_iter(None)
            pixbuf = self.iter.get_pixbuf()
            if pixbuf:
                scaled = pixbuf.scale_simple(self.width, self.height, GdkPixbuf.InterpType.BILINEAR)
                self.set_pixbuf(scaled)
        except Exception:
            pass
    
    def _update_frame(self):
        try:
            self.iter.advance(None)
            pixbuf = self.iter.get_pixbuf()
            
            if pixbuf:
                scaled = pixbuf.scale_simple(self.width, self.height, GdkPixbuf.InterpType.BILINEAR)
                self.set_pixbuf(scaled)
            
            return self.is_animating
        except Exception:
            return False
    
    def cleanup(self):
        """Stop animation timer"""
        self.is_animating = False
        if hasattr(self, 'timeout_id') and self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def start_animation(self):
        """Start the GIF animation immediately (no hover required)"""
        try:
            if not getattr(self, 'is_animating', False):
                self.is_animating = True
                if not getattr(self, 'timeout_id', None):
                    self.timeout_id = GLib.timeout_add(50, self._update_frame)
        except Exception:
            pass

    def stop_animation(self):
        """Stop the GIF animation"""
        try:
            self.is_animating = False
            if getattr(self, 'timeout_id', None):
                GLib.source_remove(self.timeout_id)
                self.timeout_id = None
        except Exception:
            pass


class RotatingSpinner(Gtk.DrawingArea):
    def __init__(self, size=48):
        super().__init__()
        try:
            self.set_size_request(size, size)
        except Exception:
            pass
        self._angle = 0.0  # degrees
        self._running = False
        self._timeout_id = None
        try:
            self.set_draw_func(self._on_draw)
        except Exception:
            try:
                self.connect('snapshot', self._on_snapshot)
            except Exception:
                try:
                    self.connect('draw', self._on_snapshot)
                except Exception:
                    pass

    def _on_draw(self, area, cr, width, height):
        try:
            w = width
            h = height
            size = min(max(1, w), max(1, h))
            cx = w / 2.0
            cy = h / 2.0
            radius = size * 0.35

            cr.save()
            cr.translate(cx, cy)
            # rotate by current angle in radians
            cr.rotate(math.radians(self._angle))

            # draw a faint circular background ring
            cr.set_line_width(max(2.0, size * 0.06))
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.12)
            cr.arc(0, 0, radius, 0, 2 * math.pi)
            cr.stroke()

            # draw an arc segment (the visible spinner)
            try:
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
            except Exception:
                pass
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
            start = 0
            end = 2.0 * math.pi * 0.6
            cr.arc(0, 0, radius, start, end)
            cr.stroke()

            cr.restore()
        except Exception:
            pass

    # fallback snapshot handler if set_draw_func wasn't available
    def _on_snapshot(self, widget, snapshot):
        try:
            cr = snapshot.append_cairo()
            w = self.get_allocated_width()
            h = self.get_allocated_height()
            self._on_draw(widget, cr, w, h)
        except Exception:
            pass

    def _tick(self):
        try:
            self._angle = (self._angle + 12.0) % 360.0
            try:
                self.queue_draw()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def start(self):
        try:
            if not self._running:
                self._running = True
                if not self._timeout_id:
                    self._timeout_id = GLib.timeout_add(40, self._tick)
        except Exception:
            pass

    def stop(self):
        try:
            self._running = False
            if self._timeout_id:
                try:
                    GLib.source_remove(self._timeout_id)
                except Exception:
                    pass
                self._timeout_id = None
        except Exception:
            pass

class WallpaperPicker(Gtk.Application):
    # Trying to add a spinner while loading
    def __init__(self):
        super().__init__(application_id="com.example.WEVideoPicker")
        self.connect("activate", self.on_activate)
        self.animated_widgets = []

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
        win.set_default_size(1200, 900)
        try:
            self.main_window = win
        except Exception:
            pass
        try:
            try:
                win.get_style_context().add_class("app-bg")
            except Exception:
                pass
        except Exception:
            pass

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        win.set_child(vbox)

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
            # Selected title and thumbnail area
            self.lbl_selected_title = Gtk.Label()
            self.lbl_selected_title.set_wrap(True)
            self.lbl_selected_title.set_wrap_mode(Pango.WrapMode.WORD)
            self.lbl_selected_title.set_ellipsize(Pango.EllipsizeMode.END)
            self.lbl_selected_title.set_text("")
            try:
                self.lbl_selected_title.set_halign(Gtk.Align.START)
                self.lbl_selected_title.set_xalign(0.0)
                self.lbl_selected_title.set_margin_start(0)
            except Exception:
                pass

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
                self.lbl_status.set_xalign(0.0)
            except Exception:
                pass

            # Thumbnail to the left of the title
            try:
                self.selected_thumb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                try:
                    self.selected_thumb_box.set_margin_end(8)
                    try:
                        # ensure the selected thumbnail area stays a fixed square
                        self.selected_thumb_box.set_size_request(180, 180)
                        self.selected_thumb_box.set_hexpand(False)
                        self.selected_thumb_box.set_vexpand(False)
                    except Exception:
                        pass
                except Exception:
                    pass
                # placeholder empty image
                placeholder = Gtk.Picture()
                try:
                    placeholder.set_content_fit(Gtk.ContentFit.COVER)
                except Exception:
                    pass
                placeholder.set_size_request(180, 180)
                self.selected_thumb_box.append(placeholder)
            except Exception:
                self.selected_thumb_box = Gtk.Box()

            title_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            title_stack.append(self.lbl_selected_title)

            # metadata labels (resolution, duration, size, created) stacked vertically
            try:
                self.meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

                self.lbl_meta_res = Gtk.Label(label="Resolution: ")
                self.lbl_meta_res.set_xalign(0.0)
                self.lbl_meta_dur = Gtk.Label(label="Duration: ")
                self.lbl_meta_dur.set_xalign(0.0)
                self.lbl_meta_size = Gtk.Label(label="Size: ")
                self.lbl_meta_size.set_xalign(0.0)
                self.lbl_meta_created = Gtk.Label(label="Created: ")
                self.lbl_meta_created.set_xalign(0.0)

                self.meta_box.append(self.lbl_meta_res)
                self.meta_box.append(self.lbl_meta_dur)
                self.meta_box.append(self.lbl_meta_size)
                self.meta_box.append(self.lbl_meta_created)
                try:
                    self.meta_box.set_visible(False)
                except Exception:
                    pass
            except Exception:
                # fallback single label if anything fails
                self.meta_box = Gtk.Box()
                self.lbl_meta_res = Gtk.Label()
                self.lbl_meta_dur = Gtk.Label()
                self.lbl_meta_size = Gtk.Label()
                self.lbl_meta_created = Gtk.Label()
                self.meta_box.append(self.lbl_meta_res)

            title_stack.append(self.meta_box)
            title_stack.append(self.lbl_status)

            status_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            status_top.append(self.selected_thumb_box)
            status_top.append(title_stack)
            status_top.set_halign(Gtk.Align.START)
        except Exception:
            pass

        try:
            self.entry_path.add_css_class("sort-container")
        except Exception:
            try:
                self.entry_path.get_style_context().add_class("sort-container")
            except Exception:
                pass
        hbox_entry.append(self.entry_path)

        # If no last path saved in state, show a quick blue "Import" button
        try:
            if not last:
                btn_quick_import = Gtk.Button(label="Test File Path")
                try:
                    btn_quick_import.add_css_class("suggested-action")
                except Exception:
                    try:
                        btn_quick_import.get_style_context().add_class("suggested-action")
                    except Exception:
                        pass
                try:
                    btn_quick_import.set_margin_start(8)
                    btn_quick_import.set_margin_end(8)
                except Exception:
                    pass
                try:
                    btn_quick_import.connect("clicked", self.on_import_clicked)
                except Exception:
                    pass
                try:
                    self.btn_quick_import = btn_quick_import
                except Exception:
                    pass
                hbox_entry.append(btn_quick_import)
        except Exception:
            pass

        btn_import = Gtk.Button(label="Import Wallpapers")
        btn_import.add_css_class("suggested-action")
        try:
            btn_import.set_margin_end(10)
        except Exception:
            pass
        btn_import.connect("clicked", self.on_import_clicked)

        # Header: title/status on left, controls on the right (Sort, Import, Help)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_valign(Gtk.Align.START)
        header.set_hexpand(True)

        try:
            header.append(status_top)
        except Exception:
            try:
                st = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                st.append(self.lbl_selected_title)
                st.append(self.lbl_status)
                st.set_halign(Gtk.Align.START)
                header.append(st)
            except Exception:
                pass

        try:
            header_spacer = Gtk.Box()
            header_spacer.set_hexpand(True)
            header.append(header_spacer)
        except Exception:
            pass

        # Controls box aligned with the title: vertical so buttons stay on top and sort sits below
        try:
            controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            controls.set_valign(Gtk.Align.START)
            try:
                controls.set_vexpand(False)
            except Exception:
                pass
            try:
                controls.set_hexpand(False)
            except Exception:
                pass
            try:
                controls.add_css_class("sort-container")
            except Exception:
                try:
                    controls.get_style_context().add_class("sort-container")
                except Exception:
                    pass

            # top row: Import + Help buttons
            try:
                top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
                top_row.set_valign(Gtk.Align.CENTER)
                top_row.append(btn_import)

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
                top_row.append(help_btn)

                controls.append(top_row)
            except Exception:
                pass

            # sort controls below the buttons (still inside the same container)
            try:
                sort_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                sort_box.set_valign(Gtk.Align.CENTER)
                try:
                    sort_box.set_margin_top(110)
                except Exception:
                    pass
                lbl_sort = Gtk.Label(label="Sort:")
                sort_box.append(lbl_sort)
                self.sort_combo = Gtk.ComboBoxText()
                for opt in ("A-Z", "Z-A", "Size on Disk", "Subscription Date"):
                    self.sort_combo.append_text(opt)
                self.sort_combo.set_active(0)
                self.sort_combo.set_tooltip_text("Sort wallpapers")
                self.sort_combo.connect("changed", self.on_sort_changed)
                sort_box.append(self.sort_combo)
                controls.append(sort_box)
            except Exception:
                pass

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

        # Compatible wallpapers section (now a Stack tab)
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

        # Create scrollable children for each tab
        compat_scrolled = Gtk.ScrolledWindow()
        compat_scrolled.set_vexpand(True)

        # Create an overlay so the spinner can sit centered over the grid without moving layout
        try:
            compat_overlay = Gtk.Overlay()
            try:
                compat_overlay.set_child(self.compat_grid)
            except Exception:
                try:
                    compat_overlay.add(self.compat_grid)
                except Exception:
                    pass
            try:
                self.compat_spinner = RotatingSpinner(48)
                try:
                    self.compat_spinner.set_halign(Gtk.Align.CENTER)
                    self.compat_spinner.set_valign(Gtk.Align.CENTER)
                except Exception:
                    pass
                try:
                    self.compat_spinner.set_visible(False)
                except Exception:
                    pass
                try:
                    compat_overlay.add_overlay(self.compat_spinner)
                except Exception:
                    try:
                        compat_overlay.add(self.compat_spinner)
                    except Exception:
                        pass
            except Exception:
                self.compat_spinner = None
            try:
                compat_scrolled.set_child(compat_overlay)
            except Exception:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                box.append(compat_overlay)
                compat_scrolled.set_child(box)
        except Exception:
            try:
                compat_scrolled.set_child(self.compat_grid)
            except Exception:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                box.append(self.compat_grid)
                compat_scrolled.set_child(box)

        incompat_scrolled = Gtk.ScrolledWindow()
        incompat_scrolled.set_vexpand(True)
        try:
                incompat_overlay = Gtk.Overlay()
                try:
                    incompat_overlay.set_child(self.incompat_grid)
                except Exception:
                    try:
                        incompat_overlay.add(self.incompat_grid)
                    except Exception:
                        pass
                try:
                    self.incompat_spinner = RotatingSpinner(48)
                    try:
                        self.incompat_spinner.set_halign(Gtk.Align.CENTER)
                        self.incompat_spinner.set_valign(Gtk.Align.CENTER)
                    except Exception:
                        pass
                    try:
                        self.incompat_spinner.set_visible(False)
                    except Exception:
                        pass
                    try:
                        incompat_overlay.add_overlay(self.incompat_spinner)
                    except Exception:
                        try:
                            incompat_overlay.add(self.incompat_spinner)
                        except Exception:
                            pass
                except Exception:
                    self.incompat_spinner = None
                # informational label shown when user opens the Incompatible Wallpapers tab
                try:
                    self.incompat_info_label = Gtk.Label()
                    try:
                        self.incompat_info_label.set_wrap(True)
                        self.incompat_info_label.set_justify(Gtk.Justification.LEFT)
                        self.incompat_info_label.set_markup(
                            "<b>About incompatible wallpapers</b>\n\n" \
                            "These items are project folders or scene projects that the KDE plugin 'Smart Video Wallpaper Reborn' cannot use " \
                            "as a compatible video wallpaper. They require a game engine to " \
                            "render these scenes - neither wallpaper engine nor the KDE plugin can handle this, \n" \
                            "Once a better option is available, this section will be updated."
                        )
                        self.incompat_info_label.set_margin_bottom(8)
                        self.incompat_info_label.set_margin_top(6)
                        self.incompat_info_label.set_visible(False)
                    except Exception:
                        pass
                except Exception:
                    self.incompat_info_label = None

                # place the info label above the overlay so it scrolls with the grid
                try:
                    incompat_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    incompat_container.append(self.incompat_info_label if self.incompat_info_label else Gtk.Label())
                    incompat_container.append(incompat_overlay)
                    try:
                        incompat_scrolled.set_child(incompat_container)
                    except Exception:
                        try:
                            box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                            box2.append(incompat_container)
                            incompat_scrolled.set_child(box2)
                        except Exception:
                            pass
                except Exception:
                    try:
                        incompat_scrolled.set_child(incompat_overlay)
                    except Exception:
                        box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                        box2.append(incompat_overlay)
                        incompat_scrolled.set_child(box2)
        except Exception:
            try:
                incompat_scrolled.set_child(self.incompat_grid)
            except Exception:
                box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                box2.append(self.incompat_grid)
                incompat_scrolled.set_child(box2)

        # Workshop (online) grid for items not owned locally
        self.workshop_grid = Gtk.Grid()
        self.workshop_grid.set_row_spacing(12)
        self.workshop_grid.set_column_spacing(12)
        self.workshop_grid.set_margin_top(12)
        self.workshop_grid.set_margin_bottom(12)
        try:
            self.workshop_grid.set_halign(Gtk.Align.CENTER)
            self.workshop_grid.set_hexpand(False)
        except Exception:
            pass
        try:
            self.workshop_grid.get_style_context().add_class("grid-bg")
        except Exception:
            pass

        workshop_scrolled = Gtk.ScrolledWindow()
        workshop_scrolled.set_vexpand(True)
        try:
            # Create a vertical container for the browse tab content
            browse_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            try:
                list_text = (
                    "1. Open Wallpaper Engine\n"
                    "2. Open the Workshop Tab\n"
                    "3. Open the \"Filter Results\" left menu\n"
                    "4. Under Type: Only Check the \"Video\" box\n"
                    "5. Uncheck everything else as it will not be compatible\n"
                )

                para_text = (
                    "The results you see are everything you should be able to download and use for now.\n"
                    "This is just a workaround for the time being - still working on finding a better solution."
                )

                # Title for the browse tab
                try:
                    title_lbl = Gtk.Label()
                    try:
                        title_lbl.set_markup("<span weight='bold' size='17000'>How to Browse Wallpapers:</span>")
                    except Exception:
                        title_lbl.set_text("How to Browse Wallpapers:")
                    try:
                        title_lbl.add_css_class("section-title")
                    except Exception:
                        try:
                            title_lbl.get_style_context().add_class("section-title")
                        except Exception:
                            pass
                    try:
                        title_lbl.set_halign(Gtk.Align.CENTER)
                    except Exception:
                        pass
                    try:
                        title_lbl.set_margin_top(100)
                        title_lbl.set_margin_bottom(2)
                    except Exception:
                        pass
                    browse_box.append(title_lbl)
                except Exception:
                    pass

                list_lbl = Gtk.Label(label=list_text)
                try:
                    list_lbl.set_wrap(True)
                    list_lbl.set_justify(Gtk.Justification.LEFT)
                except Exception:
                    pass
                try:
                    list_lbl.set_size_request(300, -1)
                except Exception:
                    pass
                try:
                    list_lbl.set_halign(Gtk.Align.CENTER)
                except Exception:
                    pass

                para_lbl = Gtk.Label(label=para_text)
                try:
                    para_lbl.set_wrap(True)
                    para_lbl.set_justify(Gtk.Justification.CENTER)
                except Exception:
                    pass
                try:
                    para_lbl.set_size_request(300, -1)
                except Exception:
                    pass
                try:
                    para_lbl.set_halign(Gtk.Align.CENTER)
                except Exception:
                    pass
                try:
                    list_lbl.set_margin_top(50)
                    list_lbl.set_margin_bottom(6)
                except Exception:
                    pass
                browse_box.append(list_lbl)

                try:
                    para_lbl.set_margin_top(6)
                    para_lbl.set_margin_bottom(6)
                except Exception:
                    pass
                browse_box.append(para_lbl)
            except Exception:
                pass

            # Open Wallpaper Engine button
            try:
                open_btn = Gtk.Button(label="Open Wallpaper Engine")
                open_btn.set_tooltip_text("Launch Wallpaper Engine via Steam")
                open_btn.add_css_class("open-we-button")
                open_btn.connect("clicked", self.on_open_wallpaper_engine)
                browse_box.append(open_btn)
            except Exception:
                pass

            try:
                workshop_overlay = Gtk.Overlay()
                try:
                    workshop_overlay.set_child(self.workshop_grid)
                except Exception:
                    try:
                        workshop_overlay.add(self.workshop_grid)
                    except Exception:
                        pass
                try:
                    self.workshop_spinner = RotatingSpinner(48)
                    try:
                        self.workshop_spinner.set_halign(Gtk.Align.CENTER)
                        self.workshop_spinner.set_valign(Gtk.Align.CENTER)
                    except Exception:
                        pass
                    try:
                        self.workshop_spinner.set_visible(False)
                    except Exception:
                        pass
                    try:
                        workshop_overlay.add_overlay(self.workshop_spinner)
                    except Exception:
                        try:
                            workshop_overlay.add(self.workshop_spinner)
                        except Exception:
                            pass
                except Exception:
                    self.workshop_spinner = None
                browse_box.append(workshop_overlay)
            except Exception:
                browse_box.append(self.workshop_grid)
            workshop_scrolled.set_child(browse_box)
        except Exception:
            wb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            wb.append(self.workshop_grid)
            workshop_scrolled.set_child(wb)

        # Tabs
        self.sections_stack = Gtk.Stack()
        try:
            self.sections_stack.add_titled(compat_scrolled, "compatible", "Compatible Wallpapers")
            self.sections_stack.add_titled(incompat_scrolled, "incompatible", "Incompatible Wallpapers")
            # Wrapping in try in case workshop connectivity is implemented
            try:
                self.sections_stack.add_titled(workshop_scrolled, "browse", "Browse Wallpapers")
            except Exception:
                pass
        except Exception:
            self.sections_stack.add_child(compat_scrolled)
            self.sections_stack.add_child(incompat_scrolled)
            try:
                self.sections_stack.add_child(workshop_scrolled)
            except Exception:
                pass

        stack_switcher = Gtk.StackSwitcher()
        try:
            stack_switcher.set_stack(self.sections_stack)
        except Exception:
            pass

        tabs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        try:
            tabs_box.set_margin_top(6)
        except Exception:
            pass
        tabs_box.append(stack_switcher)
        tabs_box.append(self.sections_stack)
        vbox.append(tabs_box)

        # Connect to stack visibility changes to lazily load incompatible items
        try:
            def _on_stack_visible(stack, pspec):
                try:
                    vis = stack.get_visible_child()
                    # show the informational paragraph when the incompatible tab becomes visible
                    try:
                        if vis is incompat_scrolled:
                            if getattr(self, 'incompat_info_label', None):
                                GLib.idle_add(self.incompat_info_label.set_visible, True)
                        else:
                            if getattr(self, 'incompat_info_label', None):
                                GLib.idle_add(self.incompat_info_label.set_visible, False)
                    except Exception:
                        pass

                    if vis is incompat_scrolled:
                        if getattr(self, "incompat_loaded", False):
                            return
                        base = getattr(self, "last_workshop_dir", None)
                        if not base:
                            GLib.idle_add(self.lbl_status.set_text, "Please import wallpapers first to scan incompatible items")
                            return
                        self.incompat_loaded = True
                        # start incompat spinner while scanning
                        try:
                            if getattr(self, 'incompat_spinner', None):
                                try:
                                    GLib.idle_add(self._start_spinner, 'incompat_spinner')
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        threading.Thread(target=self.scan_incompatible, args=(base,), daemon=True).start()
                except Exception:
                    pass

                self.sections_stack.connect("notify::visible-child", _on_stack_visible)
        except Exception:
            pass

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
            .card > button,
            .card button {
                padding: 0;
                outline-offset: 0;
            }
            .card label {
                padding-left: 8px;
                padding-right: 8px;
            }
            .card-overlay-label {
                background-color: rgba(0,0,0,0.45);
                color: #ffffff;
                padding: 6px 8px;
                margin: 0;
                border-radius: 4px 4px 0 0;
            }
            .incompatible-frame button {  
                padding: 0;
            }
            viewport {
                background-color: #2c2c2c;
            }
            .open-we-button {
                margin-left: 400px;
                margin-right: 400px;
            }
            /* input error outline */
            .input-error {
                border: 1px solid #ff4d4d;
                border-radius: 4px;
            }
            .mp4-remove-button {
                background-color: rgba(255,77,77,0.12);
                border: 1px solid rgba(255,77,77,0.18);
                border-radius: 6px;
                padding: 4px;
                color: #ffffff;
                opacity: 1.0;
            }
            .mp4-remove-button image {
                color: #ffffff;
                opacity: 1.0;
            }
            .mp4-remove-button:hover {
                background-color: rgba(255,77,77,0.18);
            }
            """
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_display(win.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass

        # Spinner start/stop helpers
        def _start_spinner_by_name(name):
            try:
                sp = getattr(self, name, None)
                if sp:
                    try:
                        sp.set_visible(True)
                        sp.start()
                    except Exception:
                        pass
            except Exception:
                pass
            return False

        def _stop_spinner_by_name(name):
            try:
                sp = getattr(self, name, None)
                if sp:
                    try:
                        sp.stop()
                        sp.set_visible(False)
                    except Exception:
                        pass
            except Exception:
                pass
            return False

        try:
            self._start_spinner = lambda name: _start_spinner_by_name(name)
            self._stop_spinner = lambda name: _stop_spinner_by_name(name)
        except Exception:
            pass

        self.clipboard = win.get_display().get_clipboard()

        # Display current video wallpaper preview and title on startup
        def _display_current_wallpaper():
            try:
                if getattr(self, "_import_failed", False):
                    return False
                current_data = get_current_video_wallpaper_data()
                if current_data and current_data.get("title"):
                    try:
                        if hasattr(self, "lbl_selected_title"):
                            esc_title = GLib.markup_escape_text(current_data.get("title", ""))
                            self.lbl_selected_title.set_markup(f"<span weight='bold' size='17000'>{esc_title}</span>")
                    except Exception:
                        if hasattr(self, "lbl_selected_title"):
                            self.lbl_selected_title.set_text(current_data.get("title", ""))
                    
                    try:
                        if hasattr(self, "selected_thumb_box"):
                            # Clear placeholder
                            while child := self.selected_thumb_box.get_first_child():
                                try:
                                    if hasattr(child, "cleanup"):
                                        try:
                                            child.cleanup()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                self.selected_thumb_box.remove(child)
                            
                            # Load a static preview (do not autoplay GIFs here)
                            thumb = self._create_square_picture(
                                current_data.get("preview"),
                                current_data.get("preview_gif"),
                                180
                            )
                            try:
                                try:
                                    thumb.set_content_fit(Gtk.ContentFit.COVER)
                                except Exception:
                                    pass
                                thumb.set_size_request(180, 180)
                                try:
                                    thumb.set_hexpand(False)
                                    thumb.set_vexpand(False)
                                except Exception:
                                    pass
                                try:
                                    thumb.set_halign(Gtk.Align.START)
                                    thumb.set_valign(Gtk.Align.START)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            wrapper = Gtk.Box()
                            try:
                                wrapper.set_size_request(180, 180)
                                wrapper.set_hexpand(False)
                                wrapper.set_vexpand(False)
                                wrapper.set_halign(Gtk.Align.CENTER)
                                wrapper.set_valign(Gtk.Align.CENTER)
                            except Exception:
                                pass
                            try:
                                wrapper.append(thumb)
                            except Exception:
                                try:
                                    wrapper.add(thumb)
                                except Exception:
                                    pass
                            try:
                                inner = thumb
                                def _cleanup_inner():
                                    try:
                                        if hasattr(inner, 'cleanup'):
                                            inner.cleanup()
                                    except Exception:
                                        pass
                                wrapper.cleanup = _cleanup_inner
                            except Exception:
                                pass
                            self.selected_thumb_box.append(wrapper)
                    except Exception:
                        pass
                    
                    # Populate metadata for the current wallpaper
                    try:
                        vid = current_data.get("video")
                        if vid:
                            meta = self.get_video_metadata(vid)
                            # Resolution
                            try:
                                if meta.get("width") and meta.get("height"):
                                    self.lbl_meta_res.set_text(f"Resolution: {meta['width']}×{meta['height']}")
                                else:
                                    self.lbl_meta_res.set_text("Resolution: —")
                            except Exception:
                                pass
                            # Duration
                            try:
                                if meta.get("duration"):
                                    self.lbl_meta_dur.set_text(f"Duration: {self._format_duration(meta['duration'])}")
                                else:
                                    self.lbl_meta_dur.set_text("Duration: —")
                            except Exception:
                                pass
                            # Size
                            try:
                                if meta.get("size") is not None:
                                    self.lbl_meta_size.set_text(f"Size: {self._human_size(meta['size'])}")
                                else:
                                    self.lbl_meta_size.set_text("Size: —")
                            except Exception:
                                pass
                            # Created
                            try:
                                if meta.get("created"):
                                    self.lbl_meta_created.set_text(f"Created: {meta['created'].strftime('%Y-%m-%d %H:%M')}")
                                else:
                                    self.lbl_meta_created.set_text("Created: —")
                            except Exception:
                                pass
                            # Show metadata box
                            try:
                                if hasattr(self, "meta_box"):
                                    self.meta_box.set_visible(True)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
            return False

        # Use timeout_add with a delay to ensure current wallpaper display runs AFTER auto-import completes
        GLib.timeout_add(500, _display_current_wallpaper)

        win.present()

    def on_import_clicked(self, button):
        raw = self.entry_path.get_text().strip()
        # initialize/import failure counter if not present
        try:
            if not hasattr(self, "_import_fail_count"):
                self._import_fail_count = 0
        except Exception:
            pass
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
            try:
                self._import_fail_count = getattr(self, "_import_fail_count", 0) + 1
            except Exception:
                self._import_fail_count = 1
            base_msg = "Could not locate workshop content folder from provided path"
            try:
                if self._import_fail_count > 1:
                    display = f"{base_msg} (x{self._import_fail_count})"
                else:
                    display = base_msg
            except Exception:
                display = base_msg

            # Mark import as failed and clear selected preview/title/metadata when import fails
            try:
                self._import_failed = True
            except Exception:
                pass
            # Clear selected preview/title/metadata when import fails
            try:
                try:
                    if hasattr(self, "selected_thumb_box") and self.selected_thumb_box is not None:
                        while child := self.selected_thumb_box.get_first_child():
                            try:
                                if hasattr(child, "cleanup"):
                                    try:
                                        child.cleanup()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            self.selected_thumb_box.remove(child)
                except Exception:
                    pass
                try:
                    if hasattr(self, "lbl_selected_title") and self.lbl_selected_title is not None:
                        self.lbl_selected_title.set_text("")
                except Exception:
                    pass
                try:
                    if hasattr(self, "meta_box") and self.meta_box is not None:
                        self.meta_box.set_visible(False)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                self.lbl_status.set_text(display)
            except Exception:
                pass
            return

        path = str(workshop_dir)
        try:
            # reset failure counter on successful detection
            self._import_fail_count = 0
            try:
                self._import_failed = False
            except Exception:
                pass
        except Exception:
            pass
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
            # Keep metadata box visible so it can be populated immediately
            if hasattr(self, "meta_box"):
                try:
                    self.meta_box.set_visible(True)
                except Exception:
                    pass
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
            try:
                if hasattr(self, "btn_quick_import"):
                    try:
                        # hide the quick import button along with the address bar and checkbox
                        self.btn_quick_import.set_visible(False)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
        self.lbl_status.set_text("Scanning... (this may take a while)")
        button.set_sensitive(False)

        # show/start compat spinner while scanning (schedule on main loop)
        try:
            if getattr(self, 'compat_spinner', None):
                try:
                    GLib.idle_add(self._start_spinner, 'compat_spinner')
                except Exception:
                    pass
        except Exception:
            pass

        threading.Thread(target=self.scan_wallpapers, args=(path, button), daemon=True).start()
        # Immediately probe for a first valid item (fast) and show its metadata so the UI updates right away
        try:
            try:
                for item_id in os.listdir(path):
                    item_dir = os.path.join(path, item_id)
                    if not os.path.isdir(item_dir):
                        continue

                    json_path = os.path.join(item_dir, "project.json")
                    if not os.path.isfile(json_path):
                        continue

                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        continue

                    # determine video file quickly
                    file_rel = data.get("file") or data.get("preview") or data.get("video")
                    video_path = None
                    if file_rel:
                        candidate = os.path.join(item_dir, file_rel)
                        if os.path.isfile(candidate) and candidate.lower().endswith((".mp4", ".webm", ".mkv")):
                            video_path = candidate

                    if not video_path:
                        for cand in ("background.mp4", "background.webm", "project.mp4"):
                            vp = os.path.join(item_dir, cand)
                            if os.path.isfile(vp):
                                video_path = vp
                                break
                    if not video_path:
                        for fname in os.listdir(item_dir):
                            if fname.lower().endswith((".mp4", ".webm", ".mkv")):
                                video_path = os.path.join(item_dir, fname)
                                break

                    if not video_path:
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

                    first_item = {
                        "title": title,
                        "video": video_path,
                        "preview": preview_static,
                        "preview_gif": preview_gif,
                        "id": item_id,
                        "dir": item_dir,
                        "size": size,
                    }
                    GLib.idle_add(self.show_first_item_metadata_item, first_item)
                    break
            except Exception:
                pass
        except Exception:
            pass

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

                    # Determine video file
                    file_rel = data.get("file") or data.get("preview") or data.get("video")
                    video_path = None
                    if file_rel:
                        candidate = os.path.join(item_dir, file_rel)
                        if os.path.isfile(candidate) and candidate.lower().endswith((".mp4", ".webm", ".mkv")):
                            video_path = candidate

                    # fallback: common filenames or any video file in folder
                    if not video_path:
                        for cand in ("background.mp4", "background.webm", "project.mp4"):
                            vp = os.path.join(item_dir, cand)
                            if os.path.isfile(vp):
                                video_path = vp
                                break
                    if not video_path:
                        for fname in os.listdir(item_dir):
                            if fname.lower().endswith((".mp4", ".webm", ".mkv")):
                                video_path = os.path.join(item_dir, fname)
                                break

                    if not video_path:
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
            
            # Clear the "Found X" status message after 3 seconds and show "Open in Explorer"
            def _clear_found_message():
                try:
                    if hasattr(self, "lbl_status"):
                        folder_uri = "file://" + quote(base_path)
                        self.lbl_status.set_markup(f"<a href='{folder_uri}'>Open in Explorer</a>")
                except Exception:
                    pass
                return False
            
            GLib.timeout_add(3000, _clear_found_message)
            
            try:
                # If we have a saved last_path, and the scanned base_path matches it,
                # show the first found item's preview and title in the top-left area.
                st = self.load_state()
                lastp = st.get("last_path") if isinstance(st, dict) else None
                try:
                    from pathlib import Path as _Path
                    match_paths = False
                    if lastp and items:
                        try:
                            if _Path(str(lastp)).resolve() == _Path(base_path).resolve():
                                match_paths = True
                        except Exception:
                            # fallback: if resolution fails, just require lastp to be truthy
                            match_paths = True

                    # Only show first item preview if no current wallpaper is configured
                    if match_paths:
                        current_wallpaper = get_current_video_wallpaper_data()
                        if not current_wallpaper or not current_wallpaper.get("video"):
                            first = items[0]

                            def _update_selected():
                                try:
                                    if hasattr(self, "selected_thumb_box"):
                                        try:
                                            while child := self.selected_thumb_box.get_first_child():
                                                try:
                                                    if hasattr(child, "cleanup"):
                                                        try:
                                                            child.cleanup()
                                                        except Exception:
                                                            pass
                                                except Exception:
                                                    pass
                                                self.selected_thumb_box.remove(child)
                                        except Exception:
                                            pass

                                        try:
                                            thumb = self._create_square_picture(first.get("preview"), first.get("preview_gif"), 180)
                                            try:
                                                try:
                                                    thumb.set_content_fit(Gtk.ContentFit.COVER)
                                                except Exception:
                                                    pass
                                                thumb.set_size_request(180, 180)
                                                try:
                                                    thumb.set_hexpand(False)
                                                    thumb.set_vexpand(False)
                                                except Exception:
                                                    pass
                                                try:
                                                    thumb.set_halign(Gtk.Align.START)
                                                    thumb.set_valign(Gtk.Align.START)
                                                except Exception:
                                                    pass
                                            except Exception:
                                                pass
                                            wrapper = Gtk.Box()
                                            try:
                                                wrapper.set_size_request(180, 180)
                                                wrapper.set_hexpand(False)
                                                wrapper.set_vexpand(False)
                                                wrapper.set_halign(Gtk.Align.CENTER)
                                                wrapper.set_valign(Gtk.Align.CENTER)
                                            except Exception:
                                                pass
                                            try:
                                                wrapper.append(thumb)
                                            except Exception:
                                                try:
                                                    wrapper.add(thumb)
                                                except Exception:
                                                    pass
                                            try:
                                                inner = thumb
                                                def _cleanup_inner():
                                                    try:
                                                        if hasattr(inner, 'cleanup'):
                                                            inner.cleanup()
                                                    except Exception:
                                                        pass
                                                wrapper.cleanup = _cleanup_inner
                                            except Exception:
                                                pass
                                            self.selected_thumb_box.append(wrapper)
                                        except Exception:
                                            pass

                                    try:
                                        esc_title = GLib.markup_escape_text(first.get("title", "Selected"))
                                        self.lbl_selected_title.set_markup(f"<span weight='bold' size='17000'>{esc_title}</span>")
                                    except Exception:
                                        pass
                                except Exception:
                                    try:
                                        self.lbl_selected_title.set_text(first.get("title", "Selected"))
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                            return False

                            GLib.idle_add(_update_selected)
                except Exception:
                    pass
            except Exception:
                pass
            # Additional MP4 paths
            try:
                st = {}
                try:
                    st = self.load_state() if hasattr(self, 'load_state') else {}
                except Exception:
                    st = {}

                # support multiple additional MP4 search paths
                try:
                    paths = []
                    try:
                        if isinstance(st, dict):
                            paths = list(st.get('additional_mp4_paths') or [])
                    except Exception:
                        paths = []
                    try:
                        if not paths and isinstance(st, dict):
                            old = st.get('additional_mp4_path')
                            if old:
                                paths = [old]
                    except Exception:
                        pass

                    for addp in paths:
                        try:
                            addp_path = Path(addp).expanduser()
                            if not (addp_path.exists() and addp_path.is_dir()):
                                continue
                            # Walk the folder tree and find mp4 files
                            for root, dirs, files in os.walk(str(addp_path)):
                                for fname in files:
                                    try:
                                        if not fname.lower().endswith('.mp4'):
                                            continue
                                        full = os.path.join(root, fname)
                                        # Skip duplicates
                                        skip = False
                                        for it in items:
                                            try:
                                                if os.path.abspath(it.get('video', '')) == os.path.abspath(full):
                                                    skip = True
                                                    break
                                            except Exception:
                                                continue
                                        if skip:
                                            continue

                                        title = os.path.splitext(fname)[0]
                                        try:
                                            size = os.path.getsize(full)
                                        except Exception:
                                            size = 0
                                        try:
                                            sub_date = os.path.getmtime(full)
                                        except Exception:
                                            sub_date = 0

                                        preview_path = None
                                        try:
                                            # Try to create a small cached thumbnail (first frame) using ffmpeg if available
                                            if shutil.which("ffmpeg") and hasattr(self, 'state_file'):
                                                try:
                                                    thumb_dir = self.state_file.parent / "thumbnails"
                                                    thumb_dir.mkdir(parents=True, exist_ok=True)
                                                    # use a stable name based on the file path
                                                    h = hashlib.sha1(full.encode('utf-8')).hexdigest()
                                                    candidate = thumb_dir / f"{h}.jpg"
                                                    if not candidate.exists():
                                                        cmd = [
                                                            "ffmpeg",
                                                            "-ss", "00:00:00",
                                                            "-i", full,
                                                            "-frames:v", "1",
                                                            "-q:v", "2",
                                                            "-vf", "scale=360:-1",
                                                            str(candidate),
                                                            "-y",
                                                        ]
                                                        try:
                                                            subprocess.run(cmd, capture_output=True, timeout=8)
                                                        except Exception:
                                                            pass
                                                    if candidate.exists():
                                                        preview_path = str(candidate)
                                                except Exception:
                                                    preview_path = None
                                        except Exception:
                                            preview_path = None

                                        items.append({
                                            'title': title,
                                            'video': full,
                                            'preview': preview_path,
                                            'preview_gif': None,
                                            'id': f"mp4:{fname}:{int(sub_date)}",
                                            'dir': root,
                                            'size': size,
                                            'sub_date': sub_date,
                                        })
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    # Update UI to reflect added mp4 count and refresh grid
                    GLib.idle_add(self.lbl_status.set_text, f"Found {len(items)} compatible wallpapers (+external mp4s)")
                    GLib.idle_add(self.show_items, items)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception as e:
            GLib.idle_add(self.lbl_status.set_text, f"Error: {str(e)}")
        finally:
            # ensure spinners are stopped on error/finish
            try:
                if getattr(self, 'compat_spinner', None):
                    try:
                        GLib.idle_add(self._stop_spinner, 'compat_spinner')
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if getattr(self, 'workshop_spinner', None):
                    try:
                        GLib.idle_add(self._stop_spinner, 'workshop_spinner')
                    except Exception:
                        pass
            except Exception:
                pass
            GLib.idle_add(button.set_sensitive, True)

    # Clean up animated widgets before clearing
    def clear_grid(self):
        for widget in self.animated_widgets:
            try:
                widget.cleanup()
            except Exception:
                pass
        self.animated_widgets.clear()
        
        while child := self.compat_grid.get_first_child():
            self.compat_grid.remove(child)

    def make_preview_widget(self, preview_static, preview_gif, width, height, autoplay=False, hover=None):
        if hover is None:
            hover = not autoplay
        if preview_gif and os.path.isfile(preview_gif):
            try:
                animated = AnimatedGifImage(preview_gif, width, height, autoplay=autoplay, hover=hover)
                self.animated_widgets.append(animated)
                return animated
            except Exception as e:
                print(f"Failed to create animated GIF: {e}")

        if preview_static and os.path.isfile(preview_static):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(preview_static, width, height, True)
                pic = Gtk.Picture.new_for_pixbuf(pixbuf)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(width, height)
                return pic
            except Exception as e:
                print(f"Failed to load static preview: {e}")

        pic = Gtk.Picture()
        pic.set_size_request(width, height)
        return pic

    def _create_square_picture(self, preview_static, preview_gif, size):
        """Return a Gtk.Picture with a center-cropped square pixbuf of `size`.

        Prefer static preview, fall back to first GIF frame if available. If neither
        exists, return an empty picture sized to `size`.
        """
        try:
            pb = None
            if preview_static and os.path.isfile(preview_static):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file(preview_static)
                except Exception:
                    pb = None
            if pb is None and preview_gif and os.path.isfile(preview_gif):
                try:
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(preview_gif)
                    it = anim.get_iter(None)
                    pb = it.get_pixbuf()
                except Exception:
                    pb = None

            if pb:
                try:
                    iw = pb.get_width()
                    ih = pb.get_height()
                    # scale up so the smallest dimension >= size, preserving aspect
                    scale = max(float(size) / iw, float(size) / ih)
                    new_w = max(1, int(iw * scale))
                    new_h = max(1, int(ih * scale))
                    scaled = pb.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
                    crop_x = max(0, (new_w - size) // 2)
                    crop_y = max(0, (new_h - size) // 2)
                    try:
                        cropped = scaled.new_subpixbuf(crop_x, crop_y, size, size)
                    except Exception:
                        # fallback to scaled resized to size x size
                        cropped = scaled.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
                    pic = Gtk.Picture.new_for_pixbuf(cropped)
                    try:
                        pic.set_content_fit(Gtk.ContentFit.COVER)
                    except Exception:
                        pass
                    pic.set_size_request(size, size)
                    return pic
                except Exception:
                    pass
        except Exception:
            pass
        p = Gtk.Picture()
        p.set_size_request(size, size)
        return p

    # stop/hide any loading spinners now that items are available
    def show_items(self, items):
        try:
            if getattr(self, 'compat_spinner', None):
                try:
                    GLib.idle_add(self._stop_spinner, 'compat_spinner')
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if getattr(self, 'workshop_spinner', None):
                try:
                    GLib.idle_add(self._stop_spinner, 'workshop_spinner')
                except Exception:
                    pass
        except Exception:
            pass

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
        
        for i, item in enumerate(items):
            frame = Gtk.Frame()
            frame.add_css_class("card")
            try:
                frame.set_margin_top(0)
                frame.set_margin_bottom(0)
                frame.set_margin_start(0)
                frame.set_margin_end(0)
                frame.set_size_request(CARD_WIDTH, CARD_HEIGHT)
            except Exception:
                pass

            # make the button and contained box expand to fill the frame
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            try:
                vbox.set_margin_top(0)
                vbox.set_margin_bottom(0)
                vbox.set_margin_start(0)
                vbox.set_margin_end(0)
                vbox.set_size_request(CARD_WIDTH, CARD_HEIGHT)
                vbox.set_hexpand(True)
                vbox.set_vexpand(True)
                vbox.set_halign(Gtk.Align.FILL)
                vbox.set_valign(Gtk.Align.FILL)
            except Exception:
                pass

            preview_static = item.get("preview")
            preview_gif = item.get("preview_gif")
            img_widget = self.make_preview_widget(preview_static, preview_gif, CARD_WIDTH, IMG_HEIGHT)
            try:
                img_widget.set_margin_top(0)
                img_widget.set_margin_bottom(0)
                img_widget.set_margin_start(0)
                img_widget.set_margin_end(0)
                img_widget.set_hexpand(True)
                img_widget.set_vexpand(True)
                img_widget.set_halign(Gtk.Align.FILL)
                img_widget.set_valign(Gtk.Align.FILL)
            except Exception:
                pass
            # Use an overlay so the label sits on top of the picture
            overlay = Gtk.Overlay()
            try:
                overlay.set_size_request(CARD_WIDTH, IMG_HEIGHT)
                overlay.set_hexpand(True)
                overlay.set_halign(Gtk.Align.FILL)
            except Exception:
                pass
            try:
                overlay.set_child(img_widget)
            except Exception:
                try:
                    overlay.add(img_widget)
                except Exception:
                    pass

            lbl = Gtk.Label(label=item["title"])
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(25)
            try:
                lbl.set_halign(Gtk.Align.CENTER)
                lbl.set_valign(Gtk.Align.END)
                lbl.set_xalign(0.5)
                lbl.set_margin_start(0)
                lbl.set_margin_end(0)
            except Exception:
                pass
            try:
                lbl.get_style_context().add_class("card-overlay-label")
            except Exception:
                pass
            try:
                overlay.add_overlay(lbl)
            except Exception:
                try:
                    overlay.add_overlay(lbl)
                except Exception:
                    pass

            vbox.append(overlay)

            btn = Gtk.Button()
            try:
                btn.set_hexpand(True)
                btn.set_vexpand(True)
                btn.set_halign(Gtk.Align.FILL)
                btn.set_valign(Gtk.Align.FILL)
            except Exception:
                pass
            btn.set_child(vbox)
            btn.item_data = item
            btn.connect("clicked", self.on_wallpaper_clicked)
            frame.set_child(btn)

            row = i // cols
            col = i % cols
            self.compat_grid.attach(frame, col, row, 1, 1)

    # Display a single item's preview and metadata in the selected area (used after import).
    def show_first_item_metadata_item(self, first):
        try:
            item = first
            if not item:
                return False

            try:
                if hasattr(self, "selected_thumb_box"):
                    try:
                        while child := self.selected_thumb_box.get_first_child():
                            try:
                                if hasattr(child, "cleanup"):
                                    try:
                                        child.cleanup()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            self.selected_thumb_box.remove(child)
                    except Exception:
                        pass

                    try:
                        thumb = self._create_square_picture(item.get("preview"), item.get("preview_gif"), 180)
                        try:
                            try:
                                thumb.set_content_fit(Gtk.ContentFit.COVER)
                            except Exception:
                                pass
                            thumb.set_size_request(180, 180)
                            try:
                                thumb.set_hexpand(False)
                                thumb.set_vexpand(False)
                            except Exception:
                                pass
                            try:
                                thumb.set_halign(Gtk.Align.START)
                                thumb.set_valign(Gtk.Align.START)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        wrapper = Gtk.Box()
                        try:
                            wrapper.set_size_request(180, 180)
                            wrapper.set_hexpand(False)
                            wrapper.set_vexpand(False)
                            wrapper.set_halign(Gtk.Align.CENTER)
                            wrapper.set_valign(Gtk.Align.CENTER)
                        except Exception:
                            pass
                        try:
                            wrapper.append(thumb)
                        except Exception:
                            try:
                                wrapper.add(thumb)
                            except Exception:
                                pass
                        try:
                            inner = thumb
                            def _cleanup_inner():
                                try:
                                    if hasattr(inner, 'cleanup'):
                                        inner.cleanup()
                                except Exception:
                                    pass
                            wrapper.cleanup = _cleanup_inner
                        except Exception:
                            pass
                        self.selected_thumb_box.append(wrapper)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                esc_title = GLib.markup_escape_text(item.get("title", "Selected"))
                self.lbl_selected_title.set_markup(f"<span weight='bold' size='17000'>{esc_title}</span>")
            except Exception:
                try:
                    self.lbl_selected_title.set_text(item.get("title", "Selected"))
                except Exception:
                    pass

            # Populate metadata if available
            try:
                vid = item.get("video")
                if vid:
                    meta = self.get_video_metadata(vid)
                    try:
                        if meta.get("width") and meta.get("height"):
                            self.lbl_meta_res.set_text(f"Resolution: {meta['width']}×{meta['height']}")
                        else:
                            self.lbl_meta_res.set_text("Resolution: —")
                    except Exception:
                        pass
                    try:
                        if meta.get("duration"):
                            self.lbl_meta_dur.set_text(f"Duration: {self._format_duration(meta['duration'])}")
                        else:
                            self.lbl_meta_dur.set_text("Duration: —")
                    except Exception:
                        pass
                    try:
                        if meta.get("size") is not None:
                            self.lbl_meta_size.set_text(f"Size: {self._human_size(meta['size'])}")
                        else:
                            self.lbl_meta_size.set_text("Size: —")
                    except Exception:
                        pass
                    try:
                        if meta.get("created"):
                            self.lbl_meta_created.set_text(f"Created: {meta['created'].strftime('%Y-%m-%d %H:%M')}")
                        else:
                            self.lbl_meta_created.set_text("Created: —")
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "meta_box"):
                            self.meta_box.set_visible(True)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception:
            pass
        return False

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
        # stop/hide incompatible spinner now that incompatible items are available
        try:
            if getattr(self, 'incompat_spinner', None):
                try:
                    GLib.idle_add(self._stop_spinner, 'incompat_spinner')
                except Exception:
                    pass
        except Exception:
            pass

        cols = 5
        CARD_WIDTH = 180
        CARD_HEIGHT = 180
        IMG_HEIGHT = (CARD_HEIGHT * 2) // 3
        
        for i, item in enumerate(items):
            frame = Gtk.Frame()
            try:
                frame.get_style_context().add_class("incompatible-frame")
                frame.set_margin_top(0)
                frame.set_margin_bottom(0)
                frame.set_margin_start(0)
                frame.set_margin_end(0)
                frame.set_size_request(CARD_WIDTH, CARD_HEIGHT)
            except Exception:
                pass

            # make the button and contained box expand to fill the frame
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            try:
                vbox.set_margin_top(0)
                vbox.set_margin_bottom(0)
                vbox.set_margin_start(0)
                vbox.set_margin_end(0)
                vbox.set_size_request(CARD_WIDTH, CARD_HEIGHT)
                vbox.set_hexpand(True)
                vbox.set_vexpand(True)
                vbox.set_halign(Gtk.Align.FILL)
                vbox.set_valign(Gtk.Align.FILL)
            except Exception:
                pass

            preview_static = item.get("preview")
            preview_gif = item.get("preview_gif")
            img = self.make_preview_widget(preview_static, preview_gif, CARD_WIDTH, IMG_HEIGHT)
            try:
                img.set_margin_top(0)
                img.set_margin_bottom(0)
                img.set_margin_start(0)
                img.set_margin_end(0)
                img.set_hexpand(True)
                img.set_vexpand(True)
                img.set_halign(Gtk.Align.FILL)
                img.set_valign(Gtk.Align.FILL)
            except Exception:
                pass

            # overlay the title on top of the image
            overlay = Gtk.Overlay()
            try:
                overlay.set_size_request(CARD_WIDTH, IMG_HEIGHT)
                overlay.set_hexpand(True)
                overlay.set_halign(Gtk.Align.FILL)
            except Exception:
                pass
            try:
                overlay.set_child(img)
            except Exception:
                try:
                    overlay.add(img)
                except Exception:
                    pass

            lbl = Gtk.Label(label=item.get("title", ""))
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(25)
            try:
                lbl.set_halign(Gtk.Align.CENTER)
                lbl.set_valign(Gtk.Align.END)
                lbl.set_xalign(0.5)
                lbl.set_margin_start(0)
                lbl.set_margin_end(0)
            except Exception:
                pass
            try:
                lbl.get_style_context().add_class("card-overlay-label")
            except Exception:
                pass
            try:
                overlay.add_overlay(lbl)
            except Exception:
                try:
                    overlay.add_overlay(lbl)
                except Exception:
                    pass
            vbox.append(overlay)

            btn = Gtk.Button()
            try:
                btn.set_hexpand(True)
                btn.set_vexpand(True)
                btn.set_halign(Gtk.Align.FILL)
                btn.set_valign(Gtk.Align.FILL)
            except Exception:
                pass
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

    # Scan a directory for incompatible wallpapers (scene projects)
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
            # Clear the "Found X" status message after 3 seconds and show "Open in Explorer"
            def _clear_incompat_found():
                try:
                    if hasattr(self, "lbl_status"):
                        try:
                            folder_uri = "file://" + quote(base_path)
                            self.lbl_status.set_markup(f"<a href='{folder_uri}'>Open in Explorer</a>")
                        except Exception:
                            self.lbl_status.set_text("")
                except Exception:
                    pass
                return False

            GLib.timeout_add(3000, _clear_incompat_found)
            # stop/hide incompatible spinner
            try:
                if getattr(self, 'incompat_spinner', None):
                    try:
                        GLib.idle_add(self._stop_spinner, 'incompat_spinner')
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            GLib.idle_add(self.lbl_status.set_text, f"Error scanning incompatible items: {e}")

    def _human_size(self, size_bytes: int) -> str:
        try:
            if size_bytes < 1024:
                return f"{size_bytes} B"
            for unit in ["KB", "MB", "GB", "TB"]:
                size_bytes /= 1024.0
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
        except Exception:
            pass
        return "Unknown"

    def _format_duration(self, seconds: float) -> str:
        try:
            secs = int(seconds)
            m, s = divmod(secs, 60)
            h, m = divmod(m, 60)
            if h:
                return f"{h:02d}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"
        except Exception:
            return "Unknown"

    def get_video_metadata(self, path: str) -> dict:
        meta = {"width": None, "height": None, "duration": None, "size": None, "created": None}
        try:
            if path and os.path.isfile(path):
                meta["size"] = os.path.getsize(path)
                try:
                    meta["created"] = datetime.fromtimestamp(os.path.getctime(path))
                except Exception:
                    meta["created"] = None

                # Try ffprobe for resolution and duration if available
                if shutil.which("ffprobe"):
                    try:
                        cmd = [
                            "ffprobe",
                            "-v", "error",
                            "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,duration",
                            "-of", "json",
                            path,
                        ]
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if res.returncode == 0 and res.stdout:
                            try:
                                jd = json.loads(res.stdout)
                                streams = jd.get("streams") or []
                                if streams:
                                    s = streams[0]
                                    meta["width"] = int(s.get("width")) if s.get("width") else None
                                    meta["height"] = int(s.get("height")) if s.get("height") else None
                                    # duration may be string
                                    dur = s.get("duration") or None
                                    if dur:
                                        try:
                                            meta["duration"] = float(dur)
                                        except Exception:
                                            meta["duration"] = None
                            except Exception:
                                pass
                    except Exception:
                        pass

        except Exception:
            pass
        return meta

    # Handle wallpaper selection
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

        # Update the selected thumbnail to show preview (static or gif)
        try:
            if hasattr(self, "selected_thumb_box"):
                try:
                    while child := self.selected_thumb_box.get_first_child():
                        try:
                            if hasattr(child, "cleanup"):
                                try:
                                    child.cleanup()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        self.selected_thumb_box.remove(child)
                except Exception:
                    pass

                try:
                    # Show a static preview immediately: prefer static preview image; if only GIF exists,
                    # render its first frame as a static picture. Store preview_gif path so we can replace
                    # it with an AnimatedGifImage after successful apply.
                    preview_static = item.get("preview")
                    preview_gif = item.get("preview_gif")
                    self._pending_selected_preview_gif = preview_gif

                    pic = None
                    try:
                        if preview_static and os.path.isfile(preview_static):
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(preview_static, 180, 180, True)
                            pic = Gtk.Picture.new_for_pixbuf(pixbuf)
                            pic.set_content_fit(Gtk.ContentFit.COVER)
                            pic.set_size_request(180, 180)
                        elif preview_gif and os.path.isfile(preview_gif):
                            try:
                                anim = GdkPixbuf.PixbufAnimation.new_from_file(preview_gif)
                                it = anim.get_iter(None)
                                pb = it.get_pixbuf()
                                if pb:
                                    scaled = pb.scale_simple(180, 180, GdkPixbuf.InterpType.BILINEAR)
                                    pic = Gtk.Picture.new_for_pixbuf(scaled)
                                    pic.set_content_fit(Gtk.ContentFit.COVER)
                                    pic.set_size_request(180, 180)
                            except Exception:
                                pic = None
                        if not pic:
                            pic = Gtk.Picture()
                            try:
                                pic.set_content_fit(Gtk.ContentFit.COVER)
                            except Exception:
                                pass
                            pic.set_size_request(180, 180)

                        # Wrap in fixed-size container to enforce square and clipping
                        wrapper = Gtk.Frame()
                        try:
                            wrapper.set_size_request(180, 180)
                            wrapper.set_hexpand(False)
                            wrapper.set_vexpand(False)
                        except Exception:
                            pass
                        try:
                            wrapper.set_child(pic)
                        except Exception:
                            try:
                                wrapper.add(pic)
                            except Exception:
                                pass
                        try:
                            def _cleanup_inner():
                                try:
                                    if hasattr(pic, 'cleanup'):
                                        pic.cleanup()
                                except Exception:
                                    pass
                            wrapper.cleanup = _cleanup_inner
                        except Exception:
                            pass
                        self.selected_thumb_box.append(wrapper)
                    except Exception:
                        try:
                            pic = Gtk.Picture()
                            pic.set_size_request(180, 180)
                            print(f"DEBUG: selected preview used static={preview_static} gif={preview_gif}")
                            wrapper = Gtk.Frame()
                            try:
                                wrapper.set_size_request(180, 180)
                                wrapper.set_hexpand(False)
                                wrapper.set_vexpand(False)
                            except Exception:
                                pass
                            try:
                                wrapper.set_child(pic)
                            except Exception:
                                try:
                                    wrapper.add(pic)
                                except Exception:
                                    pass
                            try:
                                def _cleanup_inner():
                                    try:
                                        if hasattr(pic, 'cleanup'):
                                            pic.cleanup()
                                    except Exception:
                                        pass
                                wrapper.cleanup = _cleanup_inner
                            except Exception:
                                pass
                            self.selected_thumb_box.append(wrapper)
                        except Exception:
                            pass
                except Exception:
                    pass
                # Populate metadata label under the title
                try:
                    vid = item.get("video")
                    meta = self.get_video_metadata(vid)
                    # Resolution
                    try:
                        if meta.get("width") and meta.get("height"):
                            self.lbl_meta_res.set_text(f"Resolution: {meta['width']}×{meta['height']}")
                        else:
                            self.lbl_meta_res.set_text("Resolution: —")
                    except Exception:
                        pass
                    # Duration
                    try:
                        if meta.get("duration"):
                            self.lbl_meta_dur.set_text(f"Duration: {self._format_duration(meta['duration'])}")
                        else:
                            self.lbl_meta_dur.set_text("Duration: —")
                    except Exception:
                        pass
                    # Size
                    try:
                        if meta.get("size") is not None:
                            self.lbl_meta_size.set_text(f"Size: {self._human_size(meta['size'])}")
                        else:
                            self.lbl_meta_size.set_text("Size: —")
                    except Exception:
                        pass
                    # Created
                    try:
                        if meta.get("created"):
                            self.lbl_meta_created.set_text(f"Created: {meta['created'].strftime('%Y-%m-%d %H:%M')}")
                        else:
                            self.lbl_meta_created.set_text("Created: —")
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "meta_box"):
                            self.meta_box.set_visible(True)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

        short_path = video_path.replace(str(Path.home()), "~")
        self.lbl_status.set_text(f"Applying: {short_path} …")

        try:
            self.clipboard.set(uri)
        except Exception:
            pass

        success = False
        try:
            plugin_id = "luisbocanegra.smart.video.wallpaper.reborn"
            
            # Check if the plugin is installed before attempting config changes
            if not is_kde_plugin_installed(plugin_id):
                self.lbl_status.set_text(
                    f"Error: The '{plugin_id}' plugin is not installed.\n"
                    "Please install it before setting the wallpaper.\n"
                    "Path still copied to clipboard."
                )
                return
            
            # Update config file and wallpaper plugin directly
            config_path = Path.home() / ".config/plasma-org.kde.plasma.desktop-appletsrc"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_content = f.read()
                    
                    lines = config_content.split("\n")
                    updated_lines = []
                    in_containment = False
                    
                    # Update containments (virtual desktops) to use the video wallpaper plugin
                    for line in lines:
                        # Check if we're entering a [Containments][X] section
                        if line.startswith("[Containments]["):
                            in_containment = True
                            updated_lines.append(line)
                        # Check if we're leaving the containment section
                        elif line.startswith("[") and not line.startswith("[Containments]["):
                            in_containment = False
                            updated_lines.append(line)
                        # Update wallpaperplugin lines within containment sections
                        elif in_containment and line.startswith("wallpaperplugin="):
                            updated_lines.append(f"wallpaperplugin={plugin_id}")
                        else:
                            updated_lines.append(line)
                    
                    updated_content = "\n".join(updated_lines)
                    
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    
                    success = True
                    print(f"DEBUG: Updated wallpaperplugin to '{plugin_id}' in config file")
                except Exception as e:
                    print(f"DEBUG: Error updating config file: {e}")
            
            # Still set VideoUrls using kwriteconfig6 for each containment
            if success:
                possible_containments = ["1", "2", "11", "12", "21", "22"]

                for cont_id in possible_containments:
                    group = f"Containments/{cont_id}/Wallpaper/{plugin_id}/General"

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
                        print(f"DEBUG: Set VideoUrls for group '{group}': returncode={result.returncode}")
                        
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
                raise RuntimeError("Failed to update config file")

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

            # Replace the static preview with an AnimatedGifImage and start it, if we have a preview_gif
            try:
                preview_gif = getattr(self, "_pending_selected_preview_gif", None)
                if preview_gif and os.path.isfile(preview_gif):
                    try:
                        # remove existing static child
                        if hasattr(self, "selected_thumb_box"):
                            old = self.selected_thumb_box.get_first_child()
                            try:
                                if hasattr(old, "cleanup"):
                                    try:
                                        old.cleanup()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            try:
                                if old is not None:
                                    self.selected_thumb_box.remove(old)
                            except Exception:
                                pass

                            # create animated widget and append/start it
                            print(f"DEBUG: replacing selected preview with animated gif={preview_gif}")
                            animated = AnimatedGifImage(preview_gif, 180, 180, autoplay=True, hover=False)
                            try:
                                self.animated_widgets.append(animated)
                            except Exception:
                                pass
                            # wrap animated widget in fixed frame to enforce square
                            aw = Gtk.Frame()
                            try:
                                aw.set_size_request(180, 180)
                                aw.set_hexpand(False)
                                aw.set_vexpand(False)
                            except Exception:
                                pass
                            try:
                                aw.set_child(animated)
                            except Exception:
                                try:
                                    aw.add(animated)
                                except Exception:
                                    pass
                            try:
                                def _cleanup_anim():
                                    try:
                                        if hasattr(animated, 'cleanup'):
                                            animated.cleanup()
                                    except Exception:
                                        pass
                                aw.cleanup = _cleanup_anim
                            except Exception:
                                pass
                            try:
                                self.selected_thumb_box.append(aw)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # clear pending reference
                try:
                    if hasattr(self, "_pending_selected_preview_gif"):
                        delattr(self, "_pending_selected_preview_gif")
                except Exception:
                    try:
                        del self._pending_selected_preview_gif
                    except Exception:
                        pass
            except Exception:
                pass

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

    # Try to open wallpaper engine via steam URI handler
    def on_open_wallpaper_engine(self, button):
        try:
            # Try to open Wallpaper Engine via Steam URI handler
            url = "steam://rungameid/431960"
            try:
                subprocess.Popen(["xdg-open", url])
            except Exception:
                # fallback to opening via `steam -applaunch` if available
                try:
                    subprocess.Popen(["steam", "-applaunch", "431960"])
                except Exception:
                    raise
            try:
                self.lbl_status.set_text("Opening Wallpaper Engine via Steam...")
            except Exception:
                pass
        except Exception:
            try:
                self.lbl_status.set_text("Failed to open Wallpaper Engine (no handler found).")
            except Exception:
                pass
    
    # Help Button Pop Up Window
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
6. Right click "Wallpaper Engine" from the left menu
7. Select Manage > Browse Local Files
8. Copy the file path from address bar
9. Paste it here and click "Apply"
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

            # Hint inside the path entry (placeholder) so users know what to paste
            try:
                if settings_entry:
                    try:
                        settings_entry.set_placeholder_text("Paste Steam 'Browse Local Files' path here")
                    except Exception:
                        pass
            except Exception:
                pass

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

            # Additional custom MP4 search paths (user can add multiple folders)
            try:
                state = {}
                try:
                    state = self.load_state() if hasattr(self, 'load_state') else {}
                except Exception:
                    state = {}

                add_title = Gtk.Label()
                try:
                    add_title.set_markup("<span weight='bold' size='14000'>Additional MP4 Search Paths</span>")
                except Exception:
                    add_title.set_text("Additional MP4 Search Paths")
                try:
                    add_title.set_halign(Gtk.Align.START)
                    add_title.set_margin_top(6)
                    add_title.set_margin_bottom(2)
                except Exception:
                    pass

                # container that will hold multiple rows of (Entry + Add)
                paths_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

                # helper to persist a path into state list
                def _save_path_to_state(path_text):
                    try:
                        if not path_text:
                            return
                        st = {}
                        try:
                            st = self.load_state() if hasattr(self, 'load_state') else {}
                        except Exception:
                            st = {}
                        lst = []
                        try:
                            if isinstance(st, dict):
                                lst = list(st.get('additional_mp4_paths') or [])
                        except Exception:
                            lst = []
                        # append if not present
                        if path_text and path_text not in lst:
                            lst.append(path_text)
                        try:
                            self.save_state({'additional_mp4_paths': lst})
                        except Exception:
                            pass
                        try:
                            if hasattr(self, 'lbl_status'):
                                self.lbl_status.set_text(f"Saved additional MP4 path: {path_text}")
                        except Exception:
                            pass
                    except Exception:
                        pass

                # helper to remove a path from saved state
                def _remove_path_from_state(path_text):
                    try:
                        if not path_text:
                            return
                        st = {}
                        try:
                            st = self.load_state() if hasattr(self, 'load_state') else {}
                        except Exception:
                            st = {}
                        lst = []
                        try:
                            if isinstance(st, dict):
                                lst = list(st.get('additional_mp4_paths') or [])
                        except Exception:
                            lst = []
                        try:
                            if path_text in lst:
                                lst.remove(path_text)
                        except Exception:
                            pass
                        try:
                            self.save_state({'additional_mp4_paths': lst})
                        except Exception:
                            pass
                        try:
                            if hasattr(self, 'lbl_status'):
                                self.lbl_status.set_text(f"Removed additional MP4 path: {path_text}")
                        except Exception:
                            pass
                    except Exception:
                        pass

                # factory to create a new row containing an Entry and an Add button
                def make_path_row(initial_text=""):
                    try:
                        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                        entry = Gtk.Entry()
                        try:
                            entry.set_hexpand(True)
                            entry.set_placeholder_text("Path to folder containing additional .mp4 files")
                            entry.set_text(initial_text or "")
                            # remove error styling when the user edits
                            try:
                                def _on_changed(ev):
                                    try:
                                        ev.get_style_context().remove_class('input-error')
                                        ev.set_tooltip_text(None)
                                    except Exception:
                                        pass
                                entry.connect('changed', _on_changed)
                            except Exception:
                                pass
                            if initial_text:
                                try:
                                    entry.set_editable(False)
                                    entry.set_sensitive(False)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # If an initial non-empty path is provided, show a Delete button
                        def make_open_button(entry_widget):
                            def _on_open_clicked(btn):
                                try:
                                    txt = ""
                                    try:
                                        txt = entry_widget.get_text().strip()
                                    except Exception:
                                        txt = ""
                                    if not txt:
                                        return
                                    p = Path(txt).expanduser()
                                    # attempt to open folder or file in the user's default file manager
                                    if p.exists():
                                        uri = "file://" + str(p)
                                    else:
                                        # try parent folder
                                        uri = "file://" + str(p.parent)
                                    try:
                                        Gio.AppInfo.launch_default_for_uri(uri, None)
                                    except Exception:
                                        try:
                                            subprocess.Popen(["xdg-open", str(p if p.exists() else p.parent)])
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            btn = Gtk.Button()
                            try:
                                img = Gtk.Image.new_from_icon_name("folder-open-symbolic")
                                img.set_valign(Gtk.Align.CENTER)
                                img.set_halign(Gtk.Align.CENTER)
                                btn.set_child(img)
                            except Exception:
                                try:
                                    btn.set_label("Open")
                                except Exception:
                                    pass
                            try:
                                btn.set_tooltip_text("Open folder")
                            except Exception:
                                pass
                            try:
                                btn.connect("clicked", _on_open_clicked)
                            except Exception:
                                pass
                            return btn

                        def make_delete_button(path_val, target_row):
                            def _on_delete_clicked(btn):
                                try:
                                    try:
                                        if target_row.get_parent():
                                            parent = target_row.get_parent()
                                            try:
                                                parent.remove(target_row)
                                            except Exception:
                                                try:
                                                    # fallback: hide
                                                    target_row.set_visible(False)
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass
                                    try:
                                        _remove_path_from_state(path_val)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                            btn = Gtk.Button()
                            try:
                                img = Gtk.Image.new_from_icon_name("list-remove-symbolic")
                                img.set_valign(Gtk.Align.CENTER)
                                img.set_halign(Gtk.Align.CENTER)
                                btn.set_child(img)
                            except Exception:
                                try:
                                    btn.set_label("-")
                                except Exception:
                                    pass
                            try:
                                btn.set_tooltip_text("Remove path")
                            except Exception:
                                pass
                            try:
                                btn.get_style_context().add_class("mp4-remove-button")
                            except Exception:
                                pass
                            btn.connect("clicked", _on_delete_clicked)
                            return btn

                        def _on_add_clicked(btn):
                            try:
                                txt = entry.get_text().strip()
                                if not txt:
                                    return
                                # duplicate check against saved state
                                try:
                                    st = {}
                                    try:
                                        st = self.load_state() if hasattr(self, 'load_state') else {}
                                    except Exception:
                                        st = {}
                                    saved = []
                                    try:
                                        if isinstance(st, dict):
                                            saved = list(st.get('additional_mp4_paths') or [])
                                    except Exception:
                                        saved = []
                                    if txt in saved:
                                        try:
                                            entry.get_style_context().add_class('input-error')
                                            entry.set_tooltip_text('This path is already added')
                                            entry.grab_focus()
                                        except Exception:
                                            pass
                                        return
                                except Exception:
                                    pass
                                # duplicate check against other UI rows
                                try:
                                    for other in list(paths_container.get_children()):
                                        try:
                                            # find entry widget in the other row
                                            for child in other.get_children():
                                                try:
                                                    if child is entry:
                                                        continue
                                                    if isinstance(child, Gtk.Entry):
                                                        if child.get_text().strip() == txt:
                                                            try:
                                                                entry.get_style_context().add_class('input-error')
                                                                entry.set_tooltip_text('This path is already present')
                                                                entry.grab_focus()
                                                            except Exception:
                                                                pass
                                                            raise StopIteration
                                                except Exception:
                                                    pass
                                        except StopIteration:
                                            return
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                try:
                                    _save_path_to_state(txt)
                                except Exception:
                                    pass
                                # convert this row's Add button into an Open + Delete button row
                                try:
                                    # explicitly remove the original Add button if it exists
                                    try:
                                        if 'add_btn' in locals() and add_btn is not None:
                                            try:
                                                row.remove(add_btn)
                                            except Exception:
                                                try:
                                                    add_btn.set_visible(False)
                                                except Exception:
                                                    pass
                                            try:
                                                add_btn.destroy()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                    # make entry non-editable/greyed out
                                    try:
                                        entry.set_editable(False)
                                        entry.set_sensitive(False)
                                    except Exception:
                                        pass

                                    # remove any existing children from the row, we'll rebuild it
                                    try:
                                        for child in list(row.get_children()):
                                            try:
                                                row.remove(child)
                                            except Exception:
                                                try:
                                                    child.set_visible(False)
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass

                                    # rebuild the row: entry + open button + delete button
                                    try:
                                        try:
                                            row.append(entry)
                                        except Exception:
                                            try:
                                                row.add(entry)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                    try:
                                        open_btn = make_open_button(entry)
                                        try:
                                            open_btn.set_visible(True)
                                            open_btn.set_sensitive(True)
                                        except Exception:
                                            pass
                                        try:
                                            row.append(open_btn)
                                        except Exception:
                                            try:
                                                row.add(open_btn)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                    try:
                                        del_btn = make_delete_button(txt, row)
                                        try:
                                            del_btn.set_visible(True)
                                            del_btn.set_sensitive(True)
                                        except Exception:
                                            pass
                                        try:
                                            row.append(del_btn)
                                        except Exception:
                                            try:
                                                row.add(del_btn)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                    # ensure any leftover Add buttons are removed from this row
                                    try:
                                        for child in list(row.get_children()):
                                            try:
                                                if isinstance(child, Gtk.Button):
                                                    try:
                                                        tt = child.get_tooltip_text()
                                                    except Exception:
                                                        tt = None
                                                    try:
                                                        lab = child.get_label()
                                                    except Exception:
                                                        lab = None
                                                    if tt == 'Add path' or lab == '+' or lab == 'Add':
                                                        try:
                                                            row.remove(child)
                                                            try:
                                                                child.destroy()
                                                            except Exception:
                                                                pass
                                                        except Exception:
                                                            try:
                                                                child.set_visible(False)
                                                            except Exception:
                                                                pass
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                                # append a new blank row below this one
                                try:
                                    new_row = make_path_row("")
                                    paths_container.append(new_row)
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        add_btn = Gtk.Button()
                        try:
                            img = Gtk.Image.new_from_icon_name("list-add-symbolic")
                            img.set_valign(Gtk.Align.CENTER)
                            img.set_halign(Gtk.Align.CENTER)
                            add_btn.set_child(img)
                        except Exception:
                            try:
                                add_btn.set_label("+")
                            except Exception:
                                pass
                        try:
                            add_btn.set_tooltip_text("Add path")
                        except Exception:
                            pass
                        add_btn.connect("clicked", _on_add_clicked)
                        row.append(entry)
                        # if initial text exists, create a Delete button instead
                        if initial_text:
                                try:
                                    open_btn = make_open_button(entry)
                                    try:
                                        open_btn.set_visible(True)
                                        open_btn.set_sensitive(True)
                                    except Exception:
                                        pass
                                    del_btn = make_delete_button(initial_text, row)
                                    try:
                                        del_btn.set_visible(True)
                                        del_btn.set_sensitive(True)
                                    except Exception:
                                        pass
                                    row.append(open_btn)
                                    row.append(del_btn)
                                except Exception:
                                    row.append(add_btn)
                        else:
                            row.append(add_btn)
                        return row
                    except Exception:
                        return Gtk.Box()

                # preload any existing saved paths
                try:
                    existing_list = []
                    if isinstance(state, dict):
                        existing_list = list(state.get('additional_mp4_paths') or [])
                    # if old single-value key exists, migrate it
                    if not existing_list:
                        try:
                            old = state.get('additional_mp4_path') if isinstance(state, dict) else None
                            if old:
                                existing_list = [old]
                        except Exception:
                            pass
                    # create rows for each existing path
                    if existing_list:
                        for p in existing_list:
                            try:
                                paths_container.append(make_path_row(p))
                            except Exception:
                                pass
                        # always append a blank row after existing paths to allow adding more
                        try:
                            paths_container.append(make_path_row(''))
                        except Exception:
                            pass
                    else:
                        # start with one blank row
                        paths_container.append(make_path_row(''))
                except Exception:
                    try:
                        paths_container.append(make_path_row(''))
                    except Exception:
                        pass

                settings_box.append(add_title)
                settings_box.append(paths_container)
            except Exception:
                pass

            # Place checkbox and report link on the same row, with the link right-aligned
            try:
                bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                if settings_chk:
                    bottom_row.append(settings_chk)

                # spacer will push the report button to the right
                spacer = Gtk.Box()
                try:
                    spacer.set_hexpand(True)
                except Exception:
                    pass
                bottom_row.append(spacer)

                try:
                    report_btn = Gtk.LinkButton.new_with_label(
                        "https://github.com/bomeers/WE-Video-Picker/issues",
                        "Report Issue / Contribute"
                    )
                    try:
                        report_btn.set_margin_top(6)
                    except Exception:
                        pass
                    bottom_row.append(report_btn)
                except Exception:
                    pass

                settings_box.append(bottom_row)
            except Exception:
                # Fallback: append individually
                if settings_chk:
                    settings_box.append(settings_chk)
                try:
                    report_btn = Gtk.LinkButton.new_with_label(
                        "https://github.com/bomeers/WE-Video-Picker/issues",
                        "Report Issue / Contribute"
                    )
                    settings_box.append(report_btn)
                except Exception:
                    pass

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