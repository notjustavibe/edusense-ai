[app]

# ---- identity -------------------------------------------------------------
title = EduSense AI
package.name = edusense
package.domain = org.edusense
version = 0.3.0

# ---- sources --------------------------------------------------------------
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,xml

# ---- python / kivy --------------------------------------------------------
# plyer + pyjnius + android: camera, file picker and runtime permissions
# requests stack: HTTP client for talking to the server
requirements = python3,kivy==2.3.0,plyer,pyjnius,android,requests,urllib3,chardet,idna,certifi

orientation = portrait
fullscreen = 0

# ---- android --------------------------------------------------------------
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

# INTERNET            talk to the EduSense server
# CAMERA              take class / enrollment photos
# *_EXTERNAL_STORAGE  read photos picked from the gallery (Android 12 and below)
# READ_MEDIA_IMAGES   same, Android 13+
android.permissions = INTERNET, CAMERA, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

# Allow plain http:// to the server on your LAN (see extra_manifest_application_arguments.xml)
android.extra_manifest_application_arguments = ./extra_manifest_application_arguments.xml

android.allow_backup = False

# last stable python-for-android (newer 'master' builds Python 3.14, which breaks Kivy 2.3.0)
p4a.branch = v2024.01.21

[buildozer]

log_level = 2
warn_on_root = 1
