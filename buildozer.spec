[app]
title = Debt Manager
package.name = debtmanager
package.domain = org.samir
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
source.exclude_dirs = bin, .buildozer, venv, __pycache__, .git, .github
source.exclude_patterns = *.db
version = 3.0.0

# الشعار وشاشة البداية (الملفان بجانب main.py)
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/splash.png
presplash.color = #1C4554

# المتطلبات (p4a لا يثبّت الاعتماديات تلقائيًا، لذلك تُكتب كلها صراحةً)
# - sqlite3 : ضروري وإلا يفشل import sqlite3 على الهاتف
# - python-bidi==0.4.2 : النسخ الأحدث مكتوبة بـ Rust ولا تُبنى على Android
# - six : يحتاجها python-bidi 0.4.2 ولا يثبّتها p4a تلقائيًا (بدونها لا يعمل تشكيل العربية)
requirements = python3,hostpython3,kivy==2.3.0,sqlite3,arabic-reshaper,python-bidi==0.4.2,six

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

# التطبيق لا يحتاج أي صلاحيات (قاعدة البيانات في مجلد التطبيق الخاص)

android.allow_backup = True
android.logcat_filters = *:S python:D

# نسخة p4a مستقرة مع kivy 2.3.0 / Python 3.11 / NDK 25b
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
