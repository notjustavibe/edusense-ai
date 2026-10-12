# EduSense AI

Automated classroom attendance using face recognition. Take one photo of the class and every recognised student is marked present. Also tracks per-subject attendance %, student profiles linked to roll numbers, quiz / assignment / mid / final marks, and exports.

Built for the AI Theory course (BSAI, Superior University Lahore).

![Dashboard](docs/dashboard.png)

## Features

- **One-photo attendance**: snap the class, the server detects and matches every face.
- **Per-subject sessions**: attendance % per student, per subject and overall (red below the minimum, default 75%).
- **Student profiles**: roll number, name, program, email, phone and face thumbnail.
- **Marks**: quizzes, assignments, mid-term and final per subject, with totals and percentages.
- **Manual override**: fix any mistake by tapping a name present/absent.
- **Exports**: all students in one XLSX, a PDF report per student, a ZIP of all PDFs, and a CSV per session.
- **Two clients**: Android app (Kivy) and a web dashboard, both on the same server.

## Screenshots

### Android app

| Home and session | Attendance result |
|---|---|
| ![Android app](docs/android_app.jpg) | ![Session](docs/session.png) |

### Web dashboard

| Student profile | Marks entry |
|---|---|
| ![Student profile](docs/student_profile.png) | ![Marks](docs/marks.png) |

| Enrol a student | Reports and exports |
|---|---|
| ![New student](docs/new_student.png) | ![Reports](docs/reports.png) |

### Sample photos

| Class photo | Enrolment photos |
|---|---|
| ![Class](docs/images.jpg) | ![Student 1](docs/student1.jpg) ![Student 2](docs/student2.jpg) ![Student 3](docs/student22.jpg) |

## How it works

```
Android app / Web dashboard  --HTTP-->  Flask server  -->  SQLite
                                            |
                                   face_recognition (dlib)
```

1. Enrol a student with 3-5 photos. The server stores 128-d face encodings.
2. Pick a subject, start a session and upload a class photo.
3. The server fixes EXIF rotation, downsizes to 1600 px, detects faces (HOG) and compares each against stored encodings (tolerance 0.5).
4. Matches are marked present. Fix any mistake in the app or dashboard.

**Why two parts?** `dlib` (the engine behind `face_recognition`) cannot be compiled by Buildozer, so recognition runs on a laptop/server and the phone is the camera + UI.

## Project structure

```
edusense/
├── server/                      Flask + face_recognition
│   ├── app.py                   recognition, records, marks, exports
│   ├── static/dashboard.html    records dashboard (http://<server-ip>:5000/)
│   ├── requirements.txt
│   ├── requirements-render.txt  prebuilt dlib for Render
│   └── render-build.sh
├── mobile/                      Kivy Android app (Buildozer)
│   ├── main.py                  screens + app logic
│   ├── api.py                   HTTP client for the server
│   ├── edusense.kv              UI layout
│   ├── buildozer.spec
│   └── extra_manifest_application_arguments.xml   (allows http:// on the LAN)
└── docs/                        screenshots
```

## 1. Run the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt                      # dlib compiles: needs cmake + a C++ compiler
EDUSENSE_KEY=choose-a-secret python app.py           # Windows: set EDUSENSE_KEY=... first
```

Find your laptop's LAN IP (`ipconfig` / `ip a`), e.g. `192.168.1.23`, and allow port 5000 through the firewall. Phone and laptop must be on the same Wi-Fi. Quick check from the phone browser: `http://192.168.1.23:5000/api/health`.

No Wi-Fi route? Plug in the phone with USB debugging and run `adb reverse tcp:5000 tcp:5000`, then use `http://localhost:5000` in the app.

| Env var | Purpose | Default |
|---|---|---|
| `EDUSENSE_KEY` | Optional API key (`X-API-Key` header or `?key=`) | none |
| `EDUSENSE_TOLERANCE` | Match threshold, lower is stricter | `0.5` |
| `EDUSENSE_MIN_ATTENDANCE` | Attendance % flagged red | `75` |
| `EDUSENSE_DB` | SQLite file path | `./edusense.db` |
| `PORT` | Server port | `5000` |

## 2. Build the Android app

Buildozer needs Linux (or WSL2 on Windows).

```bash
cd mobile
pip install buildozer cython
buildozer -v android debug          # first build downloads SDK/NDK, takes a while
adb install bin/*.apk
```

`buildozer.spec` pins `p4a.branch = v2024.01.21`. Newer python-for-android builds Python 3.14, which breaks Kivy 2.3.0. If the phone still shows an old version after a rebuild, run `rm -rf .buildozer/android/app bin/*.apk`, rebuild, then `adb uninstall org.edusense.edusense` before installing.

## 3. Use it

**Phone app**

1. Home: enter `http://<server-ip>:5000` and the API key, tap **Save & test**.
2. Students -> **Enroll new student**: roll no, name, 3-5 front-facing photos.
3. Home: choose the **subject**, type a session title, **Start attendance session**.
4. **Take class photo** (or pick one). Recognised students are marked present. **Open CSV** downloads the sheet.
5. **Records**: attendance % for everyone, tap a student for per-subject attendance, marks and a PDF.
6. **Marks**: pick a subject and assessment, type marks for the class, **Save marks**. Add subjects and assessments (Quiz, Assignment, Mid-term, Final) right there.
7. **Dashboard**: opens the web dashboard in the phone browser.

**Web dashboard** (`http://<server-ip>:5000/`)

- **Students**: add and edit students, attendance % per student, profile, marks per subject and PDF report.
- **Subjects & marks**: add subjects and assessments with a maximum, then fill a marks grid for the whole class. Empty box = not graded yet (not counted); type 0 for zero.
- **Sessions**: every session; click one to correct present/absent.
- **Export**: one Excel workbook for everyone (summary + one sheet per subject), or a ZIP with a PDF per student.

Assumptions: every enrolled student takes every subject, and a subject's marks percentage is total obtained / total maximum over graded assessments.

### Upgrading from an older version

```bash
cd server && source .venv/bin/activate && pip install -r requirements.txt
python app.py     # the existing database upgrades itself; old sessions go under the "General" subject
```

Rebuild the APK to get the new screens.

## 4. Deploy online (Render)

Use a **Web Service**, not a Static Site.

- Root directory: `server`
- Build command: `./render-build.sh`
- Start command: `gunicorn app:app --workers 1 --timeout 120`
- Environment: `EDUSENSE_KEY=<password>`

Free instances have 512 MB RAM and lose the database on restart. For real use take a paid instance with a persistent disk and set `EDUSENSE_DB=/data/edusense.db`. Then enter the `https://...onrender.com` URL in the app.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Status |
| GET/POST | `/api/students` | List / enrol |
| GET/PUT/DELETE | `/api/students/<id>` | Record / edit / remove |
| GET | `/api/students/<id>/report.pdf` | Student report |
| GET/POST | `/api/subjects` | Subjects |
| GET/POST | `/api/subjects/<id>/assessments` | Quiz, assignment, mid, final |
| GET/PUT | `/api/assessments/<id>/marks` | Marks entry |
| GET/POST | `/api/sessions` | Attendance sessions |
| POST | `/api/sessions/<id>/recognize` | Upload class photo |
| POST | `/api/sessions/<id>/mark` | Manual present/absent |
| GET | `/api/sessions/<id>/export.csv` | Session CSV |
| GET | `/api/export/all.xlsx` | All students workbook |
| GET | `/api/export/reports.zip` | Per-student PDFs |

## Tuning

- Enrol 3-5 photos per student in different lighting. This helps more than anything else.
- `EDUSENSE_TOLERANCE`: lower = stricter, fewer false matches, more misses.
- The HOG detector is CPU friendly but misses faces smaller than about 80 px. Stand back far enough to fit the class, not so far that faces shrink.

## Privacy

Face data is biometric data. Get students' consent, set `EDUSENSE_KEY`, use HTTPS if the server is public, and never expose the database.

## Known limits

- `plyer`'s camera launches the system camera app. On some Android 10+ phones it can crash with a file-URI error. If so, use **From gallery** or swap in `camera4kivy`.
- Only plain HTTP on the local network is configured. Use HTTPS if you expose the server.
- Not a replacement for human review. Check unmatched faces.

## Tech stack

Python, Flask, SQLite, dlib / face_recognition, Pillow, openpyxl, ReportLab, Kivy, Buildozer.

## License

MIT
