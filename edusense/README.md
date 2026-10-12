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

## 1. Run the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
EDUSENSE_KEY=choose-a-secret python app.py            # Windows: set EDUSENSE_KEY=... first
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

1. Home: enter `http://<laptop-ip>:5000` and the API key, tap **Save & test**.
2. Students -> **Enroll new student**: roll no, name, 3-5 front-facing photos.
3. Home: type a session title -> **Start attendance session**.
4. **Take class photo** (or pick one). Everyone recognised is marked present; the
   report shows present/absent. **Open CSV** downloads the sheet in the browser.

## 4. Records dashboard (profiles, marks, exports)

Open `http://<laptop-ip>:5000/` in any browser (laptop or phone). It asks for the API key if you set one.

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
