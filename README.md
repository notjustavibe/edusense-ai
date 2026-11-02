# EduSense AI

Automated classroom attendance by face recognition.

```
edusense/
├── server/                      Flask + face_recognition (runs on your laptop)
│   ├── app.py                   recognition, records, marks, exports
│   ├── static/dashboard.html    records dashboard (open http://<laptop-ip>:5000/)
│   └── requirements.txt
└── mobile/                      Kivy Android app (built with Buildozer)
    ├── main.py                  screens + app logic
    ├── api.py                   HTTP client for the server
    ├── edusense.kv              UI layout
    ├── buildozer.spec
    └── extra_manifest_application_arguments.xml   (allows http:// on the LAN)
```

**Why two parts?** `dlib` (the engine behind `face_recognition`) cannot be compiled by
Buildozer, so recognition runs on a laptop and the phone is the camera + UI.

## Accounts and login

Two kinds of users:

- **Admin** (you): logs in with the secret **admin key** as the username and **no password**. Admin can add, disable, reset and delete teachers, and delete students, subjects and assessments.
- **Teacher**: logs in with the username and password the admin gave them. Teachers can take attendance, enrol students, enter marks and view records/exports. They can change their own password (app: Home -> Password, dashboard: Change password).

Set the admin key on the server (it is **never** stored in the app or in the repo):

```bash
python -c "import secrets; print(secrets.token_urlsafe(75))"     # prints a 100-character key
EDUSENSE_ADMIN_KEY=<that key> python app.py                      # Windows: set EDUSENSE_ADMIN_KEY=... first
```

Rules: key at least 32 characters; usernames 3-32 characters (letters, digits, `. _ -`); passwords at least 8 characters and stored only as salted hashes. Five wrong logins for one username lock it for 10 minutes. Login tokens last 12 hours (`EDUSENSE_TOKEN_HOURS`); disabling a teacher or resetting their password logs them out immediately. Without `EDUSENSE_ADMIN_KEY` the admin login is disabled.

Passwords travel in clear text over plain `http://`. That is acceptable on a private classroom Wi-Fi; on the internet use HTTPS (Render provides it).

## Camera on the web page, and teacher presence

The dashboard can use the PC webcam (browser asks permission):

- **Add student -> webcam**: start the camera, press *Capture photo* 3-5 times (click a thumbnail to remove it), then *Add student*.
- **Sessions -> Take attendance with the PC camera**: pick subject + title, *Start session*, start the camera, then *Scan class*, or tick *auto-scan* (every 10-60 s). Each scan only adds people. You can also upload a photo instead.
- **Teachers -> Train face** (admin): capture 3-5 photos of a teacher. From then on, whenever a class photo is scanned (web or phone app) and that teacher's face is in it, the server logs a **sighting**. Sightings never touch attendance or marks.
- **Teachers -> Teacher presence** (admin only): per teacher, how many times the camera detected them, in how many sessions, when last, plus a list of recent detections. Admin also sees the detected teachers inside each session's detail. Teachers only see "N staff faces skipped" and cannot open any of this.
- Several detections of one teacher in the same session within 60 seconds count once (`EDUSENSE_SIGHTING_GAP`), so auto-scan does not inflate the number.

The browser only allows the camera on **https://** or **http://localhost**. On the server PC open `http://localhost:5000`; from other devices on plain `http://192.168...` the camera button will say it is blocked (file upload still works). On Render (https) it just works.

Tell teachers about the presence log and get their consent: it processes their biometric data and records when they were in class.

## 1. Run the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
EDUSENSE_ADMIN_KEY=choose-a-long-secret python app.py   # Windows: set EDUSENSE_ADMIN_KEY=... first (see Accounts and login)
```

Find your laptop's LAN IP (`ipconfig` / `ip a`), e.g. `192.168.1.23`. Allow port 5000
through the firewall. Phone and laptop must be on the same Wi-Fi.
Quick check from the phone's browser: `http://192.168.1.23:5000/api/health`

## 2. Build the Android app

Buildozer needs Linux (or WSL2 on Windows).

```bash
pip install buildozer cython
cd mobile
buildozer -v android debug          # first build downloads SDK/NDK, takes a while
buildozer android deploy run        # with the phone plugged in, USB debugging on
```

APK ends up in `mobile/bin/`.

## 3. Use it

1. Login screen: enter `http://<laptop-ip>:5000`, then log in as **Teacher** (username + password) or **Admin** (admin key).
2. Students -> **Enroll new student**: roll no, name, 3-5 front-facing photos.
3. Home: type a session title -> **Start attendance session**.
4. **Take class photo** (or pick one). Everyone recognised is marked present; the
   report shows present/absent. **Open CSV** downloads the sheet in the browser.

## 4. Records dashboard (profiles, marks, exports)

Open `http://<laptop-ip>:5000/` in any browser (laptop or phone). It shows a login page (Teacher / Admin).

- **Students**: attendance % per student (red below 75%), click a student for their profile
  (edit roll no, name, program, email, phone), attendance and marks per subject, and a PDF report.
- **Subjects & marks**: add subjects, add quizzes / assignments / mid / final with a maximum, then
  type marks for the whole class in one grid. Empty box = not graded yet (not counted); type 0 for zero.
- **Sessions**: every attendance session; click one to fix mistakes by tapping a name present/absent.
- **Export**: one Excel workbook for everyone (summary + one sheet per subject), or a ZIP with a
  PDF report for each student. A single student's PDF is in their profile.

In the phone app, pick the **subject** before starting a session; each session counts toward that
subject's attendance percentage. Change the 75% warning level with `EDUSENSE_MIN_ATTENDANCE=80`.

Assumptions: every enrolled student takes every subject, and a subject's marks percentage is
total obtained / total maximum over the assessments that have been graded.

### Upgrading from the first version

```bash
cd server && source .venv/bin/activate && uv pip install -r requirements.txt   # adds openpyxl, reportlab
python app.py     # the existing database upgrades itself; old sessions go under the "General" subject
```
Rebuild the APK too (`buildozer -v android debug`) to get the subject picker.

## Tuning

- `EDUSENSE_TOLERANCE` (default 0.5): lower = stricter, fewer false matches, more misses.
- Enrol 3-5 photos per student in different lighting; it helps more than anything else.
- HOG detector is used (CPU friendly). Faces smaller than ~80 px in the photo get missed,
  so stand back far enough to fit the class but not so far that faces shrink.

## Known limits

- `plyer`'s camera launches the system camera app; on some Android 10+ phones it can
  crash with a file-URI error. If so, use **From gallery** or swap in `camera4kivy`.
- Only HTTP on the local network is configured. Use HTTPS if you ever expose the server.
- Not tested on a physical phone from this environment - do a first test with 2-3 friends.

## v0.3.0 - records and marks inside the app

Home screen now has **Records**, **Marks** and **Dashboard** buttons.
- Records: every student with attendance %, red when below the minimum; tap one for per-subject attendance and marks, plus a PDF download.
- Marks: choose a subject, add subjects/assessments (Quiz, Assignment, Mid-term, Final) and type marks for the whole class, then Save marks.
- Dashboard: opens the web dashboard in the phone browser (exports, profile editing).

## Hosting on Render (optional)
Use a **Web Service** (not a Static Site): Root Directory `server`, Build `./render-build.sh`,
Start `gunicorn app:app --workers 1 --timeout 120`, env `EDUSENSE_ADMIN_KEY`. Free instances lose
the database on restart; use a Persistent Disk and `EDUSENSE_DB=/data/edusense.db`.

## v0.4.0 - accounts

Login screen in the app and dashboard, admin-managed teacher accounts (app: Home -> Teachers when logged in as admin; dashboard: Teachers tab). `EDUSENSE_KEY` (shared API key) is replaced by `EDUSENSE_ADMIN_KEY`.

## v0.4.1 - web camera + teacher presence

Server: new tables `teacher_encodings` and `teacher_sightings` (created automatically), `POST/DELETE /api/users/<id>/face`, `GET /api/teacher-presence` (admin). The phone app needs no rebuild for this.

## v0.5.0 - new app interface

- Redesigned phone app: app bar on every screen, rounded cards, grouped lists, bottom sheets instead of dropdowns, confirm dialogs, toasts. All sizes come from the content, so text never overlaps at any phone density or font size.
- Nothing about sessions is shown before login. After login the home screen greets you, has the "Take attendance" card, tiles for Students / Records / Marks / Dashboard / Account, and **Recent sessions** grouped as Today / Yesterday / This week / Earlier with subject filter chips.
- **A- / A+** buttons (5 steps) and a **light / dark** switch in the top bar of every screen; both are remembered.
- Android back button goes to the previous screen; the version number now lives on the Account screen only.
- Fonts: the app bundles DejaVu Sans (`mobile/assets`, free licence in `DEJAVU-LICENSE.txt`) for arrows, sun/moon and heart glyphs.

Upgrade: A fresh mobile app Layout for convenient use.