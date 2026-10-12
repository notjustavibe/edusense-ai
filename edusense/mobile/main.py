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
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup, platform

from api import Api, ApiError  # noqa: F401  (ApiError re-exported for screens)

Window.clearcolor = (0.07, 0.09, 0.13, 1)
Window.softinput_mode = "below_target"

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


def open_url(url):
    """Open a link in the phone's browser (plain webbrowser does not work reliably on Android)."""
    if platform == "android":
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        PythonActivity.mActivity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    else:
        webbrowser.open(url)


def pct_text(p):
    return "n/a" if p is None else "%.1f%%" % p


def num(x):
    return "-" if x is None else ("%g" % x)


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

    def open_dashboard(self):
        app().configure(self.ids.server_in.text, self.ids.key_in.text)
        if not app().api.base_url:
            self.set_status("Set the server URL first")
            return
        open_url(app().api.dashboard_url())


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
        open_url(app().api.csv_url(self.session_id))


# ------------------------------------------------------------------ Records
class RecordsScreen(Screen):
    """List of all students with their overall attendance percentage."""

    students = []
    min_att = 75.0

    def on_pre_enter(self, *_):
        if "list_box" not in self.ids:
            return
        self.ids.search_in.text = ""
        self.ids.status.text = "Loading..."

        def work():
            return app().api.health(), app().api.students()

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            health, self.students = res
            self.min_att = health.get("min_attendance", 75.0)
            self.ids.status.text = "%d students  |  red = attendance below %g%%" % (
                len(self.students),
                self.min_att,
            )
            self.render()

        bg(work, done)

    def render(self):
        if "list_box" not in self.ids:  # kv is still being built
            return
        q = self.ids.search_in.text.strip().lower()
        box = self.ids.list_box
        box.clear_widgets()
        for s in self.students:
            if q and q not in s["name"].lower() and q not in s["roll_no"].lower():
                continue
            p = s.get("attendance_pct")
            colour = "ff6b6b" if p is not None and p < self.min_att else "3ecf8e"
            btn = Button(
                text="%s\n%s    [color=%s]%s[/color]"
                % (escape_markup(s["roll_no"]), escape_markup(s["name"]), colour, pct_text(p)),
                markup=True,
                size_hint_y=None,
                height=70,
                halign="left",
                valign="middle",
                background_normal="",
                background_color=(0.13, 0.17, 0.25, 1),
            )
            btn.bind(size=lambda b, _s: setattr(b, "text_size", (b.width - 24, b.height)))
            btn.bind(on_release=lambda _b, s=s: self.open_student(s["id"]))
            box.add_widget(btn)

    def open_student(self, sid):
        self.manager.get_screen("detail").load(sid)
        self.manager.current = "detail"


class RecordDetailScreen(Screen):
    """One student: profile, attendance and marks per subject."""

    student_id = None

    def load(self, sid):
        self.student_id = sid
        self.ids.heading.text = "Loading..."
        self.ids.report.text = ""

        def done(res, err):
            if err:
                self.ids.heading.text = "Could not load"
                self.ids.report.text = message(err)
                return
            self.ids.heading.text = res["name"]
            self.ids.report.text = self.format(res)

        bg(lambda: app().api.student_record(sid), done)

    @staticmethod
    def format(r):
        e = escape_markup
        low = r.get("min_attendance", 75)
        lines = ["[b]%s[/b]   %s" % (e(r["roll_no"]), e(r["name"]))]
        for label, key in (("Program", "program"), ("Email", "email"), ("Phone", "phone")):
            if r.get(key):
                lines.append("%s: %s" % (label, e(r[key])))
        lines += [
            "",
            "[b]Overall attendance:[/b] %d of %d sessions  (%s)"
            % (r["present"], r["sessions"], pct_text(r["attendance_pct"])),
        ]
        for s in r["subjects"]:
            if not s["sessions"] and not s["assessments"]:
                continue
            lines += ["", "[b]%s - %s[/b]" % (e(s["code"]), e(s["name"]))]
            a = s["attendance_pct"]
            flag = "  [color=ff6b6b]below %g%%[/color]" % low if a is not None and a < low else ""
            lines.append("Attendance: %d of %d  (%s)%s" % (s["present"], s["sessions"], pct_text(a), flag))
            for x in s["assessments"]:
                lines.append("   %s:  %s / %s" % (e(x["title"]), num(x["marks"]), num(x["max_marks"])))
            if s["assessments"]:
                got = num(s["obtained"]) if s["out_of"] else "-"
                lines.append(
                    "   [b]Total (graded): %s / %s  (%s)[/b]"
                    % (got, num(s["out_of"]) if s["out_of"] else "-", pct_text(s["marks_pct"]))
                )
        return "\n".join(lines)

    def open_pdf(self):
        if self.student_id is not None:
            open_url(app().api.pdf_url(self.student_id))


# -------------------------------------------------------------------- Marks
KINDS = {"Quiz": "quiz", "Assignment": "assignment", "Mid-term": "mid", "Final": "final"}


class MarksScreen(Screen):
    """Pick subject + assessment, then type marks for the whole class."""

    subjects = {}
    assessments = {}
    assessment = None
    inputs = {}  # student_id -> (TextInput, roll_no)
    keep_subject = None
    keep_assessment = None
    token = 0

    def ready(self):
        # Spinner on_text events fire while the .kv is being built, before these widgets exist.
        return all(k in self.ids for k in ("subject_spin", "assess_spin", "grid", "status"))

    def on_pre_enter(self, *_):
        if not self.ready():
            return
        self.ids.status.text = "Loading subjects..."

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            self.subjects = {"%s - %s" % (s["code"], s["name"]): s for s in res}
            spin = self.ids.subject_spin
            spin.values = list(self.subjects)
            wanted = self.keep_subject or spin.text
            spin.text = wanted if wanted in self.subjects else (spin.values[0] if spin.values else "No subjects")
            self.keep_subject = None
            self.ids.status.text = ""
            self.load_assessments()

        bg(app().api.subjects, done)

    def clear_grid(self):
        self.ids.grid.clear_widgets()
        self.inputs = {}
        self.assessment = None

    def load_assessments(self):
        if not self.ready():
            return
        subject = self.subjects.get(self.ids.subject_spin.text)
        self.assessments = {}
        self.ids.assess_spin.values = []
        self.ids.assess_spin.text = "No assessments yet"
        self.clear_grid()
        if not subject:
            return
        sid = subject["id"]

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            if (self.subjects.get(self.ids.subject_spin.text) or {}).get("id") != sid:
                return  # the user picked another subject meanwhile
            self.assessments = {"%s (/%g)" % (a["title"], a["max_marks"]): a for a in res}
            spin = self.ids.assess_spin
            spin.values = list(self.assessments)
            if spin.values:
                wanted = self.keep_assessment
                spin.text = wanted if wanted in self.assessments else spin.values[0]
                self.keep_assessment = None
                self.load_marks()
            else:
                self.ids.status.text = "No assessments yet - add one with + Assessment"

        bg(lambda: app().api.assessments(sid), done)

    def load_marks(self):
        if not self.ready():
            return
        a = self.assessments.get(self.ids.assess_spin.text)
        self.clear_grid()
        if not a:
            return
        self.token += 1
        token = self.token
        self.ids.status.text = "Loading marks..."

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            if token != self.token:
                return  # stale answer
            self.assessment = res["assessment"]
            self.ids.status.text = "%s, out of %g. Empty = not graded yet; type 0 for zero." % (
                res["assessment"]["title"],
                res["assessment"]["max_marks"],
            )
            for m in res["marks"]:
                row = BoxLayout(size_hint_y=None, height=52, spacing=8)
                label = Label(text="%s  %s" % (m["roll_no"], m["name"]), halign="left", valign="middle", size_hint_x=0.62)
                label.bind(size=lambda l, _s: setattr(l, "text_size", (l.width, l.height)))
                box = TextInput(
                    text="" if m["marks"] is None else "%g" % m["marks"],
                    multiline=False,
                    input_filter="float",
                    hint_text="-",
                    size_hint_x=0.38,
                    padding=(10, 14),
                    background_color=(0.12, 0.15, 0.22, 1),
                    foreground_color=(1, 1, 1, 1),
                    hint_text_color=(0.55, 0.6, 0.7, 1),
                    cursor_color=(1, 1, 1, 1),
                )
                row.add_widget(label)
                row.add_widget(box)
                self.ids.grid.add_widget(row)
                self.inputs[m["student_id"]] = (box, m["roll_no"])
            if not res["marks"]:
                self.ids.status.text = "No students enrolled yet"

        bg(lambda: app().api.marks(a["id"]), done)

    def save(self):
        if not self.assessment:
            self.ids.status.text = "Pick an assessment first"
            return
        marks = {}
        for sid, (box, roll) in self.inputs.items():
            text = box.text.strip()
            if not text:
                marks[sid] = None
                continue
            try:
                marks[sid] = float(text)
            except ValueError:
                self.ids.status.text = "Marks for %s is not a number" % roll
                return
        aid = self.assessment["id"]
        self.ids.status.text = "Saving..."

        def done(res, err):
            self.ids.status.text = message(err) if err else "Saved marks for %d students" % res["saved"]

        bg(lambda: app().api.set_marks(aid, marks), done)

    def add_subject(self):
        code, name = self.ids.new_code.text.strip(), self.ids.new_name.text.strip()
        if not code or not name:
            self.ids.status.text = "Type a code and a name for the new subject"
            return

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            self.ids.new_code.text = self.ids.new_name.text = ""
            self.keep_subject = "%s - %s" % (res["code"], res["name"])
            self.on_pre_enter()

        bg(lambda: app().api.create_subject(code, name), done)

    def add_assessment(self):
        subject = self.subjects.get(self.ids.subject_spin.text)
        if not subject:
            self.ids.status.text = "Pick a subject first"
            return
        try:
            out_of = float(self.ids.max_in.text)
        except ValueError:
            self.ids.status.text = "Type the maximum marks first (for example 10)"
            return

        def done(res, err):
            if err:
                self.ids.status.text = message(err)
                return
            self.ids.max_in.text = ""
            self.keep_assessment = "%s (/%g)" % (res["title"], res["max_marks"])
            self.load_assessments()

        kind = KINDS.get(self.ids.kind_spin.text, "quiz")
        bg(lambda: app().api.create_assessment(subject["id"], kind, "", out_of), done)


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
