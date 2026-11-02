"""Navigation and sidebar layout use temporary collections only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import customtkinter as ctk
from PIL import Image
from retro_beaten.app import RetroBeatenApp
from retro_beaten.storage.preferences import load_preferences


class SidebarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.geometry("1000x720")
        self.root.attributes("-alpha", 0)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(str(error[1]))
        self.addCleanup(self.close)
        with patch("retro_beaten.app.create_window", return_value=self.root):
            self.app = RetroBeatenApp(self.temp.name)
        cover = Path(self.temp.name)/"cover.png"
        Image.new("RGB",(150,200),"navy").save(cover)
        self.app.games = [dict(id=i,name=f"Game {i}",status=status,platform="PC",cover_path=cover)
                          for i,status in enumerate(("playing","beaten","wishlist","dropped"))]
        self.app.recommendations = [dict(id="recommended:9:PC",igdb_id=9,name="Suggestion",status="recommended",
                                         platform="PC",cover_path=cover)]
        self.app.refresh_library()
        self.settle()

    def settle(self):
        self.root.after(450,self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.errors,[])

    def close(self):
        for callback in self.root.tk.call("after","info"):
            self.root.tk.call("after","cancel",callback)
        self.root.destroy()

    def test_collapse_persists_and_gives_space_without_rebuilding_collection(self):
        app=self.app
        before=app.database_path.read_bytes()
        width=app.content.winfo_width()
        app.sidebar.toggle()
        self.settle()
        self.assertFalse(app.sidebar.body.winfo_ismapped())
        self.assertTrue(app.sidebar.rail.winfo_ismapped())
        self.assertGreater(app.content.winfo_width(),width+100)
        self.assertFalse(load_preferences(app.preferences_path)["sidebar_expanded"])
        app.sidebar.toggle()
        self.settle()
        self.assertTrue(app.sidebar.body.winfo_ismapped())
        self.assertEqual(app.database_path.read_bytes(),before)
        self.assertEqual(len(app.games),4)

    def test_navigation_filters_only_visible_records_and_search_still_works(self):
        app=self.app
        for scope,key in (("playing","playing"),("beaten","beaten:PC"),("wishlist","wishlist"),
                          ("recommended","recommended"),("dropped","dropped")):
            app.sidebar.buttons[scope].invoke()
            self.settle()
            self.assertEqual(set(app.library_area._shelf_cache),{key})
            self.assertEqual(len(app.games),4)
            self.assertEqual(len(app.recommendations),1)
        app.select_shelf("all")
        app.local_search.query.set("Game 1")
        self.settle()
        self.assertEqual(set(app.library_area._shelf_cache),{"beaten:PC"})
        self.assertEqual(app.sidebar.counts["all"],4)

    def test_exhibition_restores_collapsed_rail_and_selected_shelf(self):
        app=self.app
        app.sidebar.toggle()
        app.select_shelf("beaten")
        self.settle()
        app.toggle_exhibition()
        self.settle()
        self.assertFalse(app.sidebar.winfo_ismapped())
        self.assertFalse(app.header.winfo_ismapped())
        self.assertTrue(app.exhibition_bar.winfo_ismapped())
        app.exit_exhibition()
        self.settle()
        self.assertTrue(app.sidebar.rail.winfo_ismapped())
        self.assertFalse(app.sidebar.expanded)
        self.assertEqual(app.shelf_scope,"beaten")
        self.assertTrue(app.local_search.winfo_ismapped())

    def test_small_window_keeps_search_and_sidebar_controls_within_window(self):
        self.root.geometry("980x620")
        self.settle()
        app=self.app
        entry=app.local_search.entry
        self.assertGreater(entry.winfo_width(),120)
        self.assertLessEqual(entry.winfo_rootx()+entry.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
        self.assertGreater(app.library_area._parent_canvas.winfo_height(),300)
        self.assertLess(app.sidebar.body._parent_canvas.yview()[1],1)
        app.sidebar.body._parent_canvas.yview_moveto(1)
        self.settle()
        self.assertGreater(app.sidebar.tools.winfo_rooty(),self.root.winfo_rooty())

    def test_sidebar_wheel_does_not_scroll_the_collection(self):
        app=self.app
        self.root.geometry("980x620")
        self.settle()
        library=app.library_area._parent_canvas
        sidebar=app.sidebar.body._parent_canvas
        before=library.yview()
        sidebar.event_generate("<MouseWheel>",delta=-120,x=30,y=200)
        self.settle()
        self.assertGreater(sidebar.yview()[0],0)
        self.assertEqual(library.yview(),before)
        before=sidebar.yview()
        app.library_area._shelf_viewport.surface.event_generate("<MouseWheel>",delta=-120,x=100,y=200)
        self.settle()
        self.assertEqual(sidebar.yview(),before)
        self.assertGreater(library.yview()[0],0)
