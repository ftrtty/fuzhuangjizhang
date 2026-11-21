
[app]
title = 服装记工本
package.name = fuzhuangjigongben
package.domain = com.example

source.dir = .
source.include_exts = py,kv,png,jpg,txt,json,ttf,otf

version = 1.0
requirements = python3,kivy

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/icon.png

android.minapi = 26
android.api = 36
android.ndk = 28c
android.archs = arm64-v8a,armeabi-v7a

android.accept_sdk_license = True
android.permissions =
android.allow_backup = True

# python-for-android pip 兼容修复
p4a.branch = develop
p4a.commit = 5865575

[buildozer]
log_level = 2
warn_on_root = 1

