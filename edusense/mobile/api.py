"""Thin HTTP client for the EduSense server."""
import os

import requests


class ApiError(Exception):
    """Raised with a message that is safe to show to the user."""


class Api:
    def __init__(self, base_url="", key=""):
        self.base_url = base_url
        self.key = key

    def configure(self, base_url, key=""):
        base_url = (base_url or "").strip().rstrip("/")
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = "http://" + base_url
        self.base_url = base_url
        self.key = (key or "").strip()

    # ------------------------------------------------------------ plumbing
    def _request(self, method, path, timeout=20, **kwargs):
        if not self.base_url:
            raise ApiError("Set the server URL first")
        headers = {"X-API-Key": self.key} if self.key else {}
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
        return url + ("?key=" + self.key if self.key else "")

    def dashboard_url(self):
        return self.base_url + "/" + ("?key=" + self.key if self.key else "")

    def csv_url(self, session_id):
        url = "%s/api/sessions/%d/export.csv" % (self.base_url, session_id)
        return url + ("?key=" + self.key if self.key else "")
