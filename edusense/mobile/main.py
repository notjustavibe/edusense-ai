"""EduSense AI - Android client (Kivy).

Takes a classroom photo, sends it to the EduSense server, shows who was marked present,
and gives access to student records, marks and (for the admin) teacher accounts.
"""
import datetime
import os
import threading
import time
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.storage.jsonstore import JsonStore
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen, SlideTransition
from kivy.utils import escape_markup, platform

HERE = os.path.dirname(os.path.abspath(__file__))
# DejaVu Sans (free licence) supplies the arrows, sun/moon and heart glyphs that Roboto lacks.
LabelBase.register(
    name="Icons",
    fn_regular=os.path.join(HERE, "assets", "DejaVuSans.ttf"),
    fn_bold=os.path.join(HERE, "assets", "DejaVuSans-Bold.ttf"),
)

import widgets  # noqa: E402,F401  (registers Select, Sheet, Dialog, Toast, Collapse for the .kv)
from api import Api, ApiError  # noqa: E402,F401
from theme import Theme  # noqa: E402
from widgets import Dialog, initials  # noqa: E402

VERSION = "0.5.0"
DEFAULT_URL = "http://192.168.1.10:5000"
Window.softinput_mode = "below_target"


# ------------------------------------------------------------------ helpers
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


def make(cls_name, **props):
    """Build a kv-defined widget; its custom properties only exist after __init__, so set them afterwards."""
    w = getattr(Factory, cls_name)()
    for k, v in props.items():
        setattr(w, k, v)
    return w


def say(label, text, tone="info"):
    """Show text in a Notice widget (an empty text hides it)."""
    label.tone = tone
    label.text = text


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


def ask_text(title, hint, on_ok, password=True, message_text=""):
    Dialog(title=title, message=message_text, hint=hint, with_field=True, password=password, ok_text="OK", on_ok=on_ok).open()


def confirm(title, text, on_yes, ok_text="Yes", danger=True):
    Dialog(title=title, message=text, ok_text=ok_text, danger=danger, on_ok=on_yes).open()


def pct_text(p):
    return "n/a" if p is None else "%.1f%%" % p


def pct_tone(p, low):
    if p is None:
        return "muted"
    return "bad" if p < low else "ok"


def num(x):
    return "-" if x is None else ("%g" % x)


def e(text):
    return escape_markup(str(text if text is not None else ""))


def parse_dt(text):
    try:
        return datetime.datetime.strptime((text or "")[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def when_group(dt):
    if dt is None:
        return "Earlier"
    days = (datetime.date.today() - dt.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return "This week"
    return "Earlier"


def when_text(dt, raw=""):
    if dt is None:
        return (raw or "")[:16]
    return "%d %s, %s" % (dt.day, dt.strftime("%b"), dt.strftime("%H:%M"))


def host_of(url):
    return (url or "").replace("https://", "").replace("http://", "").rstrip("/")


def greeting():
    hour = datetime.datetime.now().hour
    return "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")


# ------------------------------------------------------------------- Splash
class SplashScreen(Screen):
    pass


# --------------------------------------------------------------------- Home
class HomeScreen(Screen):
    subjects = {}  # select label -> subject dict from the server
    sessions = []
    code = None  # subject-code filter for recent sessions (None = all)

    def on_pre_enter(self, *_):
        if "who" not in self.ids:  # Kivy fires this while the .kv is still being built
            return
        api = app().api
        ids = self.ids
        ids.hello.text = greeting()
        ids.who.text = e(api.username or "Admin")
        ids.role.text = "%s  ·  %s" % ("Administrator" if api.is_admin else "Teacher", e(host_of(api.base_url)))
        ids.tile6.icon, ids.tile6.title, ids.tile6.sub = (
            ("⚙", "Teachers", "Accounts and access") if api.is_admin else ("↻", "Refresh", "Reload sessions")
        )
        say(ids.status, "")
        self.refresh()

    def refresh(self):
        self.load_subjects()
        self.refresh_sessions()

    def tile6(self):
        if app().api.is_admin:
            app().go("teachers")
        else:
            self.refresh()
            app().toast("Refreshing...")

    def log_out(self):
        confirm("Log out", "You will need to sign in again on this phone.", app().log_out, ok_text="Log out", danger=False)

    def load_subjects(self):
        if not app().api.base_url:
            return

        def done(res, err):
            if err or not res:
                return
            self.subjects = {"%s - %s" % (s["code"], s["name"]): s for s in res}
            sel = self.ids.subject_spin
            sel.values = list(self.subjects)
            if sel.text not in self.subjects:
                sel.text = sel.values[0]

        bg(app().api.subjects, done)

    def refresh_sessions(self):
        if not app().api.base_url:
            return

        def done(res, err):
            if err:
                return
            self.sessions = res
            self.render_sessions()

        bg(app().api.sessions, done)

    def set_code(self, code):
        self.code = code
        self.render_sessions()

    def render_sessions(self):
        ids = self.ids
        chips = ids.chip_box
        chips.clear_widgets()
        codes = []
        for s in self.sessions:
            c = s.get("subject_code")
            if c and c not in codes:
                codes.append(c)
        if self.code not in codes:
            self.code = None
        if len(codes) > 1:
            for label, code in [("All", None)] + [(c, c) for c in codes]:
                chip = make("Chip", text=label, active=(code == self.code))
                chip.bind(on_release=lambda _c, code=code: self.set_code(code))
                chips.add_widget(chip)
        ids.chip_box.parent.opacity = 1 if len(codes) > 1 else 0
        ids.chip_box.parent.height = ids.chip_box.height if len(codes) > 1 else 0

        box = ids.sessions_box
        box.clear_widgets()
        rows = [s for s in self.sessions if not self.code or s.get("subject_code") == self.code]
        if not rows:
            box.add_widget(Factory.Muted(text="No sessions yet. Start one above to take attendance."))
            return
        groups = {}
        for s in rows:
            dt = parse_dt(s["created_at"])
            s["_dt"] = dt
            groups.setdefault(when_group(dt), []).append(s)
        for name in ("Today", "Yesterday", "This week", "Earlier"):
            items = groups.get(name)
            if not items:
                continue
            box.add_widget(Factory.Cap(text="%s  ·  %d" % (name.upper(), len(items))))
            for s in items:
                label = "%s - %s" % (s["subject_code"], s["title"]) if s.get("subject_code") else s["title"]
                meta = "  ·  ".join(x for x in (s.get("subject_code"), when_text(s["_dt"], s["created_at"])) if x)
                row = make("SessionRow", title=e(s["title"]), meta=e(meta), badge="%d present" % s["present"])
                row.bind(on_release=lambda _r, s=s, label=label: self.open_session(s["id"], label, s))
                box.add_widget(row)

    def start_session(self):
        ids = self.ids
        title = ids.title_in.text.strip()
        if not title:
            say(ids.status, "Type a session title first", "warn")
            return
        subject = self.subjects.get(ids.subject_spin.text)
        if subject is None:
            # never guess: a session in the wrong subject would corrupt attendance percentages
            say(ids.status, "Subjects are still loading - wait a moment, then pick a subject", "warn")
            self.load_subjects()
            return
        ids.start_btn.disabled = True

        def done(res, err):
            ids.start_btn.disabled = False
            if err:
                say(ids.status, message(err), "bad")
                return
            say(ids.status, "")
            ids.title_in.text = ""
            self.open_session(res["id"], "%s - %s" % (subject["code"], res["title"]), {"subject_name": subject["name"]})

        bg(lambda: app().api.create_session(title, subject["id"]), done)

    def open_session(self, sid, title, info=None):
        sub = ""
        if info:
            dt = info.get("_dt")
            sub = "  ·  ".join(x for x in (info.get("subject_name"), when_text(dt) if dt else "") if x)
        app().sm.get_screen("session").load(sid, title, sub)
        app().go("session")

    def open_dashboard(self):
        open_url(app().api.dashboard_url())


# ----------------------------------------------------------------- Students
class StudentsScreen(Screen):
    def on_pre_enter(self, *_):
        if "list_box" in self.ids:
            self.refresh()

    def refresh(self):
        say(self.ids.status, "Loading...")

        def done(res, err):
            box = self.ids.list_box
            box.clear_widgets()
            if err:
                say(self.ids.status, message(err), "bad")
                return
            say(self.ids.status, "" if res else "No students yet. Enroll the first one below.")
            for s in res:
                card = Factory.Card(padding=[dp(14), dp(14)])
                row = Factory.HRow()
                row.add_widget(Factory.Avatar(text=initials(s["name"]), pos_hint={"center_y": 0.5}))
                col = Factory.VBox(pos_hint={"center_y": 0.5})
                col.add_widget(Factory.Txt(text="[b]%s[/b]" % e(s["name"])))
                col.add_widget(Factory.Muted(text="%s  ·  %d photo%s" % (e(s["roll_no"]), s["samples"], "" if s["samples"] == 1 else "s")))
                row.add_widget(col)
                btn = Factory.MiniBtn(text="Delete", pos_hint={"center_y": 0.5})
                btn.bind(on_release=lambda _b, s=s: self.delete(s))
                row.add_widget(btn)
                card.add_widget(row)
                box.add_widget(card)

        bg(app().api.students, done)

    def delete(self, student):
        def go():
            def done(_res, err):
                if err:
                    app().toast(message(err), bad=True)
                else:
                    app().toast("Deleted %s" % student["name"])
                self.refresh()

            bg(lambda: app().api.delete_student(student["id"]), done)

        confirm("Delete student", "Delete %s (%s) and all their face photos and attendance?" % (student["name"], student["roll_no"]), go, ok_text="Delete")



# ------------------------------------------------------------------- Enroll
class EnrollScreen(Screen):
    photos = []

    def on_pre_enter(self, *_):
        if "roll_in" not in self.ids:
            return
        self.photos = []
        self.ids.roll_in.text = ""
        self.ids.name_in.text = ""
        self.update_count()
        say(self.ids.status, "")

    def update_count(self):
        n = len(self.photos)
        self.ids.count.text = "[b]%d photo%s[/b] selected" % (n, "" if n == 1 else "s") if n else "No photos yet"

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
        ids = self.ids
        roll, name = ids.roll_in.text.strip(), ids.name_in.text.strip()
        if not roll or not name or not self.photos:
            say(ids.status, "Enter a roll number, a name and add at least one photo.", "warn")
            return
        say(ids.status, "Uploading...")
        ids.enroll_btn.disabled = True
        photos = list(self.photos)

        def done(res, err):
            ids.enroll_btn.disabled = False
            if err:
                say(ids.status, message(err), "bad")
                return
            say(ids.status, "Enrolled %s (%d samples added)" % (e(res["name"]), res["added_samples"]), "ok")
            ids.roll_in.text = ids.name_in.text = ""
            self.clear_photos()

        bg(lambda: app().api.enroll(roll, name, photos), done)


# ------------------------------------------------------------------ Session
class SessionScreen(Screen):
    session_id = None

    def load(self, sid, title, subtitle=""):
        self.session_id = sid
        ids = self.ids
        ids.bar.title = title
        ids.subtitle.text = e(subtitle) or "One photo of the class can mark many students."
        say(ids.result, "")
        ids.stats.open = False
        ids.present_box.clear_widgets()
        ids.absent_box.clear_widgets()
        ids.p_count.text = ids.a_count.text = "0"
        self.refresh()

    def capture(self, source):
        app().get_photo(source, self.send)

    def send(self, path):
        if not path:
            return
        say(self.ids.result, "Recognizing faces... this can take about 10 seconds.")

        def done(res, err):
            ids = self.ids
            if err:
                say(ids.result, message(err), "bad")
                return
            marked = len(res["recognized"])
            names = ", ".join("%s%s" % (e(r["name"]), "" if r["new"] else " (already)") for r in res["recognized"])
            say(ids.result, ("Marked: " + names) if names else "Nobody was recognised in this photo.", "ok" if names else "warn")
            ids.st_seen.number = str(res["faces_detected"])
            ids.st_marked.number = str(marked)
            ids.st_unknown.number = str(res["unknown"])
            ids.stats.open = True
            self.refresh()

        bg(lambda: app().api.recognize(self.session_id, path), done)

    def refresh(self):
        def done(res, err):
            ids = self.ids
            if err:
                say(ids.result, message(err), "bad")
                return
            for box, key, tone, count in (
                (ids.present_box, "present", "ok", ids.p_count),
                (ids.absent_box, "absent", "bad", ids.a_count),
            ):
                box.clear_widgets()
                count.text = str(len(res[key]))
                if not res[key]:
                    box.add_widget(Factory.Muted(text="Nobody here yet." if key == "present" else "Everyone is present."))
                for p in res[key]:
                    box.add_widget(make("PersonRow", name=e(p["name"]), sub=e(p["roll_no"]), tone=tone))

        bg(lambda: app().api.attendance(self.session_id), done)

    def open_csv(self):
        open_url(app().api.csv_url(self.session_id))


# ------------------------------------------------------------------ Records
class RecordsScreen(Screen):
    """All students with their overall attendance percentage."""

    students = []
    min_att = 75.0
    only_risk = BooleanProperty(False)

    def on_pre_enter(self, *_):
        if "list_box" not in self.ids:
            return
        self.ids.search_in.text = ""
        self.only_risk = False
        say(self.ids.status, "Loading...")

        def work():
            return app().api.me(), app().api.students()

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            health, self.students = res
            self.min_att = health.get("min_attendance", 75.0)
            say(self.ids.status, "")
            self.ids.chip_risk.text = "Below %g%%" % self.min_att
            self.render()

        bg(work, done)

    def set_risk(self, value):
        self.only_risk = value
        self.render()

    def render(self):
        if "list_box" not in self.ids:
            return
        q = self.ids.search_in.text.strip().lower()
        box = self.ids.list_box
        box.clear_widgets()
        shown = 0
        for s in self.students:
            if q and q not in s["name"].lower() and q not in s["roll_no"].lower():
                continue
            p = s.get("attendance_pct")
            if self.only_risk and not (p is not None and p < self.min_att):
                continue
            shown += 1
            card = make("StudentCard", 
                name=e(s["name"]), roll=e(s["roll_no"]), initials=initials(s["name"]),
                pct_text=pct_text(p), pct=p or 0, tone=pct_tone(p, self.min_att),
            )
            card.bind(on_release=lambda _c, s=s: self.open_student(s["id"]))
            box.add_widget(card)
        if not shown:
            box.add_widget(Factory.Muted(text="No students match."))

    def open_student(self, sid):
        app().sm.get_screen("detail").load(sid)
        app().go("detail")


class RecordDetailScreen(Screen):
    """One student: profile, attendance and marks per subject."""

    student_id = None

    def load(self, sid):
        self.student_id = sid
        ids = self.ids
        ids.d_name.text, ids.d_roll.text, ids.d_info.text = "Loading...", "", ""
        ids.subjects_box.clear_widgets()

        def done(res, err):
            if err:
                ids.d_name.text = "Could not load"
                ids.d_info.text = e(message(err))
                return
            self.show(res)

        bg(lambda: app().api.student_record(sid), done)

    def show(self, r):
        ids = self.ids
        low = r.get("min_attendance", 75)
        ids.avatar.text = initials(r["name"])
        ids.d_name.text = e(r["name"])
        ids.d_roll.text = e(r["roll_no"])
        info = ["%s: %s" % (label, e(r[key])) for label, key in (("Program", "program"), ("Email", "email"), ("Phone", "phone")) if r.get(key)]
        ids.d_info.text = "\n".join(info)
        ids.d_overall.text = "%d of %d sessions attended" % (r["present"], r["sessions"])
        ids.d_pill.text = pct_text(r["attendance_pct"])
        ids.d_pill.tone = ids.d_bar.tone = pct_tone(r["attendance_pct"], low)
        ids.d_bar.value = r["attendance_pct"] or 0
        box = ids.subjects_box
        box.clear_widgets()
        for s in r["subjects"]:
            if not s["sessions"] and not s["assessments"]:
                continue
            a = s["attendance_pct"]
            card = make("SubjectCard", 
                code=e(s["code"]), sname=e(s["name"]), pct_text=pct_text(a), pct=a or 0, tone=pct_tone(a, low),
                line="Attendance: %d of %d sessions%s" % (s["present"], s["sessions"], "  (below %g%%)" % low if a is not None and a < low else ""),
            )
            rows = card.ids.rows
            if s["assessments"]:
                rows.add_widget(Factory.Cap(text="MARKS"))
            for x in s["assessments"]:
                rows.add_widget(make("KV", k=e(x["title"]), v="%s / %s" % (num(x["marks"]), num(x["max_marks"]))))
            if s["assessments"]:
                got = num(s["obtained"]) if s["out_of"] else "-"
                rows.add_widget(make("KV", k="[b]Total (graded)[/b]", v="%s / %s  (%s)" % (got, num(s["out_of"]) if s["out_of"] else "-", pct_text(s["marks_pct"]))))
            box.add_widget(card)
        if not box.children:
            box.add_widget(Factory.Muted(text="No attendance or marks recorded yet."))

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
    panel = StringProperty("")  # '', 'subject' or 'assessment': which "add" form is open

    def ready(self):
        return all(k in self.ids for k in ("subject_spin", "assess_spin", "grid", "status"))

    def toggle_panel(self, name):
        self.panel = "" if self.panel == name else name

    def on_pre_enter(self, *_):
        if not self.ready():
            return
        self.panel = ""
        say(self.ids.status, "Loading subjects...")

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            self.subjects = {"%s - %s" % (s["code"], s["name"]): s for s in res}
            sel = self.ids.subject_spin
            sel.values = list(self.subjects)
            wanted = self.keep_subject or sel.text
            sel.text = wanted if wanted in self.subjects else (sel.values[0] if sel.values else "")
            self.keep_subject = None
            say(self.ids.status, "")
            self.load_assessments()

        bg(app().api.subjects, done)

    def clear_grid(self):
        self.ids.grid.clear_widgets()
        self.inputs = {}
        self.assessment = None
        self.ids.grid_card.opacity = 0
        self.ids.save_btn.disabled = True

    def load_assessments(self, *_):
        if not self.ready():
            return
        subject = self.subjects.get(self.ids.subject_spin.text)
        self.assessments = {}
        self.ids.assess_spin.values = []
        self.ids.assess_spin.text = ""
        self.clear_grid()
        if not subject:
            return
        sid = subject["id"]

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            if (self.subjects.get(self.ids.subject_spin.text) or {}).get("id") != sid:
                return  # the user picked another subject meanwhile
            self.assessments = {"%s (/%g)" % (a["title"], a["max_marks"]): a for a in res}
            sel = self.ids.assess_spin
            sel.values = list(self.assessments)
            if sel.values:
                wanted = self.keep_assessment
                sel.text = wanted if wanted in self.assessments else sel.values[0]
                self.keep_assessment = None
                self.load_marks()
            else:
                say(self.ids.status, "No assessments yet. Tap + Assessment to add a quiz, assignment, mid-term or final.", "warn")

        bg(lambda: app().api.assessments(sid), done)

    def load_marks(self, *_):
        if not self.ready():
            return
        a = self.assessments.get(self.ids.assess_spin.text)
        self.clear_grid()
        if not a:
            return
        self.token += 1
        token = self.token
        say(self.ids.status, "Loading marks...")

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            if token != self.token:
                return  # stale answer
            self.assessment = res["assessment"]
            say(self.ids.status, "%s, out of %g. Leave empty for not graded yet; type 0 for zero." % (e(res["assessment"]["title"]), res["assessment"]["max_marks"]))
            for m in res["marks"]:
                row = make("MarkRow", name=e(m["name"]), roll=e(m["roll_no"]), value="" if m["marks"] is None else "%g" % m["marks"])
                self.ids.grid.add_widget(row)
                self.inputs[m["student_id"]] = (row.ids.box, m["roll_no"])
            if not res["marks"]:
                say(self.ids.status, "No students enrolled yet", "warn")
            else:
                self.ids.grid_card.opacity = 1
                self.ids.save_btn.disabled = False

        bg(lambda: app().api.marks(a["id"]), done)

    def save(self):
        if not self.assessment:
            say(self.ids.status, "Pick an assessment first", "warn")
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
                say(self.ids.status, "Marks for %s is not a number" % e(roll), "bad")
                return
        aid = self.assessment["id"]
        self.ids.save_btn.disabled = True

        def done(res, err):
            self.ids.save_btn.disabled = False
            if err:
                say(self.ids.status, message(err), "bad")
            else:
                app().toast("Saved marks for %d students" % res["saved"])

        bg(lambda: app().api.set_marks(aid, marks), done)

    def add_subject(self):
        code, name = self.ids.new_code.text.strip(), self.ids.new_name.text.strip()
        if not code or not name:
            say(self.ids.status, "Type a code and a name for the new subject", "warn")
            return

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            self.ids.new_code.text = self.ids.new_name.text = ""
            self.keep_subject = "%s - %s" % (res["code"], res["name"])
            self.on_pre_enter()
            self.panel = ""
            app().toast("Subject added")

        bg(lambda: app().api.create_subject(code, name), done)

    def add_assessment(self):
        subject = self.subjects.get(self.ids.subject_spin.text)
        if not subject:
            say(self.ids.status, "Pick a subject first", "warn")
            return
        try:
            out_of = float(self.ids.max_in.text)
        except ValueError:
            say(self.ids.status, "Type the maximum marks first (for example 10)", "warn")
            return

        def done(res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            self.ids.max_in.text = ""
            self.keep_assessment = "%s (/%g)" % (res["title"], res["max_marks"])
            self.panel = ""
            self.load_assessments()
            app().toast("Assessment added")

        kind = KINDS.get(self.ids.kind_spin.text, "quiz")
        bg(lambda: app().api.create_assessment(subject["id"], kind, "", out_of), done)


# -------------------------------------------------------------------- Login
class LoginScreen(Screen):
    admin_mode = BooleanProperty(False)

    def fill(self):
        if "server_in" not in self.ids:
            return
        self.ids.server_in.text = app().api.base_url
        self.ids.user_in.text = app().saved_user

    def on_pre_enter(self, *_):
        self.fill()

    def set_mode(self, admin):
        self.admin_mode = admin
        say(self.ids.status, "")

    def login(self):
        ids = self.ids
        if ids.login_btn.disabled:  # a login is already in flight (double tap)
            return
        app().api.configure(ids.server_in.text)
        if not app().api.base_url:
            say(ids.status, "Enter the server address", "warn")
            return
        if self.admin_mode:
            user, password = ids.key_in.text.strip(), ""
        else:
            user, password = ids.user_in.text.strip(), ids.pass_in.text
        if not user or (not self.admin_mode and not password):
            say(ids.status, "Enter your admin key" if self.admin_mode else "Enter your username and password", "warn")
            return
        say(ids.status, "Signing in...")
        ids.login_btn.disabled = True

        def done(res, err):
            ids.login_btn.disabled = False
            if err:
                say(ids.status, message(err), "bad")
                return
            ids.pass_in.text = ""
            ids.key_in.text = ""
            say(ids.status, "")
            app().remember_login(user if not self.admin_mode else "")
            app().reset_to("home")

        bg(lambda: app().api.login(user, password), done)


# ------------------------------------------------------- Teachers (admin only)
class TeachersScreen(Screen):
    def on_pre_enter(self, *_):
        if "list_box" in self.ids:
            self.refresh()

    def refresh(self):
        say(self.ids.status, "Loading...")

        def done(res, err):
            box = self.ids.list_box
            box.clear_widgets()
            if err:
                say(self.ids.status, message(err), "bad")
                return
            say(self.ids.status, "" if res else "No teachers yet. Add one above.")
            for u in res:
                card = make("TeacherCard", name=e(u["username"]), active=bool(u["active"]))
                actions = card.ids.actions
                for text, handler in (
                    ("Reset", lambda u=u: self.reset(u)),
                    ("Disable" if u["active"] else "Enable", lambda u=u: self.toggle(u)),
                    ("Delete", lambda u=u: self.delete(u)),
                ):
                    b = Factory.GhostBtn(text=text, height=dp(46))
                    b.bind(on_release=lambda _b, h=handler: h())
                    actions.add_widget(b)
                box.add_widget(card)

        bg(app().api.users, done)

    def add(self):
        user, password = self.ids.new_user.text.strip(), self.ids.new_pass.text
        if not user or not password:
            say(self.ids.status, "Type a username and a password for the teacher", "warn")
            return

        def done(_res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            self.ids.new_user.text = ""
            self.ids.new_pass.text = ""
            app().toast("Teacher created")
            self.refresh()

        bg(lambda: app().api.create_user(user, password), done)

    def _then_refresh(self, work, note=""):
        def done(_res, err):
            if err:
                say(self.ids.status, message(err), "bad")
            else:
                if note:
                    app().toast(note)
                self.refresh()

        bg(work, done)

    def reset(self, u):
        ask_text("New password for %s" % u["username"], "At least 8 characters",
                 lambda pw: self._then_refresh(lambda: app().api.update_user(u["id"], password=pw), "Password changed"))

    def toggle(self, u):
        self._then_refresh(lambda: app().api.update_user(u["id"], active=not u["active"]))

    def delete(self, u):
        confirm("Delete teacher", "Delete %s? Their login stops working." % u["username"],
                lambda: self._then_refresh(lambda: app().api.delete_user(u["id"]), "Teacher deleted"), ok_text="Delete")



# ------------------------------------------------------------------ Account
class AccountScreen(Screen):
    def on_pre_enter(self, *_):
        if "old_in" not in self.ids:
            return
        api = app().api
        for name in ("old_in", "new_in", "new2_in"):
            self.ids[name].text = ""
        self.ids.avatar.text = initials(api.username or "A")
        self.ids.a_name.text = e(api.username or "Admin")
        self.ids.a_role.text = "Administrator" if api.is_admin else "Teacher"
        self.ids.about.text = "EduSense AI  v%s" % VERSION
        say(self.ids.status, "")

    def submit(self):
        old, new, new2 = self.ids.old_in.text, self.ids.new_in.text, self.ids.new2_in.text
        if new != new2:
            say(self.ids.status, "The two new passwords do not match", "warn")
            return

        def done(_res, err):
            if err:
                say(self.ids.status, message(err), "bad")
                return
            for name in ("old_in", "new_in", "new2_in"):
                self.ids[name].text = ""
            say(self.ids.status, "Password changed", "ok")

        bg(lambda: app().api.change_password(old, new), done)


# ---------------------------------------------------------------------- App
class EduSenseApp(App):
    title = "EduSense AI"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Kivy loads edusense.kv BEFORE build(), and the screens already need
        # self.api / self.th, so settings and the API client are created here.
        self.store = JsonStore(os.path.join(self.user_data_dir, "settings.json"))
        server = self.store.get("server") if self.store.exists("server") else {}
        auth = self.store.get("auth") if self.store.exists("auth") else {}
        ui = self.store.get("ui") if self.store.exists("ui") else {}
        self.saved_user = server.get("user", "")
        self.api = Api(server.get("url", DEFAULT_URL), auth.get("token", ""), auth.get("role", ""), auth.get("username", ""))
        self.api.on_auth_lost = lambda: Clock.schedule_once(lambda _dt: self.go_login("Session expired - please log in again"), 0)
        self.th = Theme(dark=ui.get("dark", True), scale=ui.get("scale", 1.0))
        self.th.bind(dark=self.save_ui, scale=self.save_ui)
        self.th.bind(bg=lambda _t, c: setattr(Window, "clearcolor", c))
        Window.clearcolor = self.th.bg
        self.stack = []
        self.sm = None

    def save_ui(self, *_):
        try:
            self.store.put("ui", dark=self.th.dark, scale=self.th.scale)
        except Exception:
            pass  # a settings write must never crash the UI

    def build(self):
        self.sm = self.root.ids.sm
        self.sm.transition = SlideTransition(duration=0.18)
        Window.bind(on_keyboard=self.on_key)
        return self.root

    # ------------------------------------------------------------ navigation
    def go(self, name):
        if name == self.sm.current:
            return
        self.stack.append(self.sm.current)
        self.sm.transition.direction = "left"
        self.sm.current = name

    def back(self):
        if not self.stack:
            return False
        self.sm.transition.direction = "right"
        self.sm.current = self.stack.pop()
        return True

    def reset_to(self, name):
        self.stack = []
        self.sm.transition.direction = "left" if name == "home" else "right"
        self.sm.current = name

    def on_key(self, _window, key, *_args):
        if key == 27:  # Android back button / Esc
            for w in Window.children[:]:
                if isinstance(w, ModalView):
                    w.dismiss()
                    return True
            return self.back()  # False at the top level: lets the system close the app
        return False

    def toast(self, text, bad=False):
        self.root.ids.toast.show(text, bad)

    # ---------------------------------------------------------------- start
    def on_start(self):
        login = self.sm.get_screen("login")
        login.fill()
        if self.api.token and self.api.base_url:

            def done(res, err):
                if err:
                    say(login.ids.status, "" if getattr(err, "login_required", False) else message(err), "bad")
                    self.reset_to("login")
                    return
                self.api.role, self.api.username = res["role"], res["username"]
                self.reset_to("home")

            bg(self.api.me, done)
        else:
            Clock.schedule_once(lambda _dt: self.reset_to("login"), 0.4)
        if platform == "android":
            from android.permissions import Permission, request_permissions

            request_permissions([Permission.CAMERA, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    def remember_login(self, user):
        # not "key=": that name is already a parameter of JsonStore.put()
        self.saved_user = user or self.saved_user
        self.store.put("server", url=self.api.base_url, user=self.saved_user)
        self.store.put("auth", token=self.api.token, role=self.api.role, username=self.api.username)

    def forget_login(self):
        if self.store.exists("auth"):
            self.store.delete("auth")

    def go_login(self, note=""):
        self.forget_login()
        login = self.sm.get_screen("login")
        self.reset_to("login")
        if "status" in login.ids:
            say(login.ids.status, note, "warn")

    def log_out(self):
        api = self.api
        threading.Thread(target=api.logout, daemon=True).start()  # invalidate the token on the server
        self.go_login()

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

        filechooser.open_file(on_selection=picked, filters=[("Images", "*.jpg", "*.jpeg", "*.png")])

    def on_pause(self):
        return True  # keep the app alive while the camera app is in front


if __name__ == "__main__":
    EduSenseApp().run()
