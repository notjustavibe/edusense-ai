"""EduSense AI - Android client (Kivy).

Takes a classroom photo, sends it to the EduSense server, shows who was marked present.
"""
import os
import threading
import time
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.storage.jsonstore import JsonStore
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen
from kivy.utils import platform

from api import Api, ApiError  # noqa: F401  (ApiError re-exported for screens)

Window.clearcolor = (0.07, 0.09, 0.13, 1)

DEFAULT_URL = "http://192.168.1.10:5000"


def bg(work, done):
    """Run work() off the UI thread, then call done(result, error) on it."""

    def runner():
        try:
            result, error = work(), None
        except Exception as exc:  # shown to the user, never crashes the app
            result, error = None, exc
        Clock.schedule_once(lambda _dt: done(result, error), 0)

    threading.Thread(target=runner, daemon=True).start()


def message(err):
    return str(err) if isinstance(err, ApiError) else "Unexpected error: %s" % err


def app():
    return App.get_running_app()


# --------------------------------------------------------------------- Home
class HomeScreen(Screen):
    subjects = {}  # spinner label -> subject dict from the server

    def on_pre_enter(self, *_):
        if "server_in" not in self.ids:
            # First screen: Kivy fires this while the .kv is still being built and the
            # widgets don't exist yet. EduSenseApp.on_start calls it again afterwards.
            return
        self.ids.server_in.text = app().api.base_url
        self.ids.key_in.text = app().api.key
        self.refresh_sessions()
        self.load_subjects()

    def load_subjects(self):
        if not app().api.base_url:
            return

        def done(res, err):
            if err or not res:
                return
            self.subjects = {"%s - %s" % (s["code"], s["name"]): s for s in res}
            spin = self.ids.subject_spin
            spin.values = list(self.subjects)
            if spin.text not in self.subjects:
                spin.text = spin.values[0]

        bg(app().api.subjects, done)

    def set_status(self, text):
        self.ids.status.text = text

    def save_and_test(self):
        app().configure(self.ids.server_in.text, self.ids.key_in.text)
        self.set_status("Testing connection...")

        def done(res, err):
            if err:
                self.set_status(message(err))
            else:
                self.set_status("Connected - %d students enrolled" % res["students"])
                self.refresh_sessions()
                self.load_subjects()

        bg(app().api.health, done)

    def refresh_sessions(self):
        if not app().api.base_url:
            return

        def done(res, err):
            box = self.ids.sessions_box
            box.clear_widgets()
            if err:
                return
            for s in res:
                s["label"] = "%s - %s" % (s["subject_code"], s["title"]) if s.get("subject_code") else s["title"]
                btn = Button(
                    text="%s\n%s  |  %d present" % (s["label"], s["created_at"][:16], s["present"]),
                    size_hint_y=None,
                    height=64,
                    halign="center",
                    background_normal="",
                    background_color=(0.13, 0.17, 0.25, 1),
                )
                btn.bind(on_release=lambda _b, s=s: self.open_session(s["id"], s["label"]))
                box.add_widget(btn)

        bg(app().api.sessions, done)

    def start_session(self):
        title = self.ids.title_in.text.strip()
        if not title:
            self.set_status("Type a session title first")
            return
        app().configure(self.ids.server_in.text, self.ids.key_in.text)
        subject = self.subjects.get(self.ids.subject_spin.text)
        if subject is None:
            # never guess: a session in the wrong subject would corrupt attendance percentages
            self.set_status("Subjects not loaded yet - tap Save & test, then pick a subject")
            self.load_subjects()
            return

        def done(res, err):
            if err:
                self.set_status(message(err))
            else:
                self.ids.title_in.text = ""
                label = "%s - %s" % (subject["code"], res["title"]) if subject else res["title"]
                self.open_session(res["id"], label)

        bg(lambda: app().api.create_session(title, subject["id"] if subject else None), done)

    def open_session(self, sid, title):
        self.manager.get_screen("session").load(sid, title)
        self.manager.current = "session"


# ----------------------------------------------------------------- Students
class StudentsScreen(Screen):
    def on_pre_enter(self, *_):
        self.refresh()

    def refresh(self):
        self.ids.status.text = "Loading..."

        def done(res, err):
            box = self.ids.list_box
            box.clear_widgets()
            if err:
                self.ids.status.text = message(err)
                return
            self.ids.status.text = "%d enrolled" % len(res)
            for s in res:
                row = Button(
                    text="%s  -  %s   (%d photos)   [tap to delete]"
                    % (s["roll_no"], s["name"], s["samples"]),
                    size_hint_y=None,
                    height=52,
                    background_normal="",
                    background_color=(0.13, 0.17, 0.25, 1),
                )
                row.bind(on_release=lambda b, s=s: self.delete(b, s))
                box.add_widget(row)

        bg(app().api.students, done)

    def delete(self, button, student):
        # first tap arms the button, second tap deletes
        if not getattr(button, "armed", False):
            button.armed = True
            button.background_color = (0.75, 0.2, 0.2, 1)
            button.text = "Tap again to delete %s" % student["name"]
            Clock.schedule_once(lambda _dt: self.refresh(), 4)
            return

        def done(_res, err):
            self.ids.status.text = message(err) if err else "Deleted"
            self.refresh()

        bg(lambda: app().api.delete_student(student["id"]), done)


# ------------------------------------------------------------------- Enroll
class EnrollScreen(Screen):
    def on_pre_enter(self, *_):
        self.photos = []
        self.ids.roll_in.text = ""
        self.ids.name_in.text = ""
        self.update_count()
        self.ids.status.text = ""

    def update_count(self):
        self.ids.count.text = "Photos: %d  (3-5 clear, front-facing shots work best)" % len(
            self.photos
        )

    def add_photo(self, source):
        def got(path):
            if path:
                self.photos.append(path)
                self.update_count()

        app().get_photo(source, got)

    def clear_photos(self):
        self.photos = []
        self.update_count()

    def submit(self):
        roll, name = self.ids.roll_in.text.strip(), self.ids.name_in.text.strip()
        if not roll or not name or not self.photos:
            self.ids.status.text = "Need a roll number, a name and at least one photo"
            return
        self.ids.status.text = "Uploading..."
        photos = list(self.photos)

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
            else:
                self.ids.status.text = "Enrolled %s (%d samples added)" % (
                    res["name"],
                    res["added_samples"],
                )
                self.clear_photos()

        bg(lambda: app().api.enroll(roll, name, photos), done)


# ------------------------------------------------------------------ Session
class SessionScreen(Screen):
    session_id = None
    title = ""

    def load(self, sid, title):
        self.session_id, self.title = sid, title
        self.ids.heading.text = title
        self.ids.result.text = "Take a photo of the class - one photo can mark many students."
        self.ids.report.text = ""
        self.refresh()

    def capture(self, source):
        app().get_photo(source, self.send)

    def send(self, path):
        if not path:
            return
        self.ids.result.text = "Recognizing faces... (can take ~10 s)"

        def done(res, err):
            if err:
                self.ids.result.text = message(err)
                return
            names = ", ".join(
                "%s%s" % (r["name"], "" if r["new"] else " (already)") for r in res["recognized"]
            )
            self.ids.result.text = "Faces detected: %d\nMarked: %s\nUnrecognized: %d" % (
                res["faces_detected"],
                names or "nobody",
                res["unknown"],
            )
            self.refresh()

        bg(lambda: app().api.recognize(self.session_id, path), done)

    def refresh(self):
        def done(res, err):
            if err:
                self.ids.report.text = message(err)
                return
            lines = ["PRESENT (%d)" % len(res["present"])]
            lines += ["  %s  %s" % (p["roll_no"], p["name"]) for p in res["present"]]
            lines += ["", "ABSENT (%d)" % len(res["absent"])]
            lines += ["  %s  %s" % (a["roll_no"], a["name"]) for a in res["absent"]]
            self.ids.report.text = "\n".join(lines)

        bg(lambda: app().api.attendance(self.session_id), done)

    def open_csv(self):
        webbrowser.open(app().api.csv_url(self.session_id))


# ---------------------------------------------------------------------- App
class EduSenseApp(App):
    title = "EduSense AI"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Kivy loads edusense.kv BEFORE build(), and the first screen already
        # needs self.api, so settings and the API client are created here.
        self.store = JsonStore(os.path.join(self.user_data_dir, "settings.json"))
        saved = self.store.get("server") if self.store.exists("server") else {}
        self.api = Api(saved.get("url", DEFAULT_URL), saved.get("api_key", ""))

    def on_start(self):
        self.root.get_screen("home").on_pre_enter()  # fill the first screen now that it exists
        if platform == "android":
            from android.permissions import Permission, request_permissions

            request_permissions(
                [
                    Permission.CAMERA,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ]
            )

    def configure(self, url, key):
        self.api.configure(url, key)
        # not "key=": that name is already a parameter of JsonStore.put()
        self.store.put("server", url=self.api.base_url, api_key=self.api.key)

    def get_photo(self, source, callback):
        """source = 'camera' or 'gallery'. callback(path_or_None) runs on the UI thread."""
        if source == "camera":
            try:
                from plyer import camera

                path = os.path.join(self.user_data_dir, "shot_%d.jpg" % int(time.time()))

                def done(filepath):
                    ok = bool(filepath) and os.path.exists(filepath)
                    Clock.schedule_once(lambda _dt: callback(filepath if ok else None), 0)
                    return True  # tell plyer to keep the file

                camera.take_picture(filename=path, on_complete=done)
                return
            except (NotImplementedError, ImportError):
                pass  # desktop testing: fall through to the file picker
        from plyer import filechooser

        def picked(selection):
            Clock.schedule_once(lambda _dt: callback(selection[0] if selection else None), 0)

        filechooser.open_file(
            on_selection=picked, filters=[("Images", "*.jpg", "*.jpeg", "*.png")]
        )

    def on_pause(self):
        return True  # keep the app alive while the camera app is in front


if __name__ == "__main__":
    EduSenseApp().run()
