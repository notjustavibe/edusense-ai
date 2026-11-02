"""Thin HTTP client for the EduSense server."""
import os

import requests


class ApiError(Exception):
    """Raised with a message that is safe to show to the user."""

    def __init__(self, message, login_required=False):
        super().__init__(message)
        self.login_required = login_required


class Api:
    def __init__(self, base_url="", token="", role="", username=""):
        self.base_url = base_url
        self.token = token
        self.role = role
        self.username = username
        self.on_auth_lost = None  # called (from any thread) when the server says "log in again"

    @staticmethod
    def clean_url(base_url):
        base_url = (base_url or "").strip().rstrip("/")
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = "http://" + base_url
        return base_url

    def configure(self, base_url):
        url = self.clean_url(base_url)
        if url != self.base_url:  # a token only works on the server that issued it
            self.set_auth("", "", "")
        self.base_url = url

    def set_auth(self, token, role, username):
        self.token, self.role, self.username = token or "", role or "", username or ""

    @property
    def is_admin(self):
        return self.role == "admin"

    # ------------------------------------------------------------ plumbing
    def _request(self, method, path, timeout=20, **kwargs):
        if not self.base_url:
            raise ApiError("Set the server URL first")
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        try:
            resp = requests.request(
                method, self.base_url + path, headers=headers, timeout=timeout, **kwargs
            )
        except requests.Timeout:
            raise ApiError("Server timed out - is it busy or unreachable?")
        except requests.RequestException:
            raise ApiError("Cannot reach server - same Wi-Fi? URL and port correct?")
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code == 401 and path != "/api/login":
            self.set_auth("", "", "")
            if self.on_auth_lost:
                self.on_auth_lost()
            raise ApiError(data.get("error") or "Please log in again", login_required=True)
        if not resp.ok:
            raise ApiError(data.get("error") or "Server error (HTTP %d)" % resp.status_code)
        return data

    @staticmethod
    def _image_part(field, path):
        with open(path, "rb") as fh:
            return (field, (os.path.basename(path), fh.read(), "image/jpeg"))

    # ----------------------------------------------------------- endpoints
    def health(self):
        return self._request("GET", "/api/health", timeout=6)

    # ---------------------------------------------------------------- accounts
    def login(self, username, password=""):
        """Teacher: username + password.  Admin: the admin key as username, empty password."""
        data = self._request("POST", "/api/login", timeout=12, json={"username": username, "password": password})
        self.set_auth(data["token"], data["role"], data["username"])
        return data

    def logout(self):
        try:
            self._request("POST", "/api/logout", timeout=6)
        except ApiError:
            pass
        self.set_auth("", "", "")

    def me(self):
        return self._request("GET", "/api/me", timeout=8)

    def change_password(self, old_password, new_password):
        return self._request("POST", "/api/me/password", json={"old_password": old_password, "new_password": new_password})

    def users(self):
        return self._request("GET", "/api/users")["users"]

    def create_user(self, username, password):
        return self._request("POST", "/api/users", json={"username": username, "password": password})

    def update_user(self, user_id, **fields):
        return self._request("PUT", "/api/users/%d" % user_id, json=fields)

    def delete_user(self, user_id):
        return self._request("DELETE", "/api/users/%d" % user_id)

    def students(self):
        return self._request("GET", "/api/students")["students"]

    def enroll(self, roll_no, name, photo_paths):
        files = [self._image_part("image", p) for p in photo_paths]
        return self._request(
            "POST",
            "/api/students",
            timeout=90,
            data={"roll_no": roll_no, "name": name},
            files=files,
        )

    def delete_student(self, student_id):
        return self._request("DELETE", "/api/students/%d" % student_id)

    def sessions(self):
        return self._request("GET", "/api/sessions")["sessions"]

    def subjects(self):
        return self._request("GET", "/api/subjects")["subjects"]

    def create_subject(self, code, name):
        return self._request("POST", "/api/subjects", json={"code": code, "name": name})

    def create_session(self, title, subject_id=None):
        body = {"title": title}
        if subject_id is not None:
            body["subject_id"] = subject_id
        return self._request("POST", "/api/sessions", json=body)

    def attendance(self, session_id):
        return self._request("GET", "/api/sessions/%d/attendance" % session_id)

    def recognize(self, session_id, photo_path):
        return self._request(
            "POST",
            "/api/sessions/%d/recognize" % session_id,
            timeout=90,
            files=[self._image_part("image", photo_path)],
        )

    def mark(self, session_id, student_id, present=True):
        return self._request(
            "POST",
            "/api/sessions/%d/mark" % session_id,
            json={"student_id": student_id, "present": present},
        )

    def student_record(self, student_id):
        return self._request("GET", "/api/students/%d" % student_id)

    def assessments(self, subject_id):
        return self._request("GET", "/api/subjects/%d/assessments" % subject_id)["assessments"]

    def create_assessment(self, subject_id, kind, title, max_marks):
        return self._request(
            "POST",
            "/api/subjects/%d/assessments" % subject_id,
            json={"kind": kind, "title": title, "max_marks": max_marks},
        )

    def marks(self, assessment_id):
        return self._request("GET", "/api/assessments/%d/marks" % assessment_id)

    def set_marks(self, assessment_id, marks):
        """marks: {student_id: number or None}."""
        return self._request(
            "PUT",
            "/api/assessments/%d/marks" % assessment_id,
            json={"marks": {str(k): v for k, v in marks.items()}},
        )

    def pdf_url(self, student_id):
        url = "%s/api/students/%d/report.pdf" % (self.base_url, student_id)
        return url + ("?token=" + self.token if self.token else "")

    def dashboard_url(self):
        return self.base_url + "/"  # the dashboard has its own login page

    def csv_url(self, session_id):
        url = "%s/api/sessions/%d/export.csv" % (self.base_url, session_id)
        return url + ("?token=" + self.token if self.token else "")
