#!/usr/bin/env python3
"""Add independent Google Play / Direct APK Android product flavors.

Play ID:   com.kisastream.kisa_stream
Direct ID: com.kisastream.kisa_stream.direct
Run inside your existing generated Flutter project using:
    python3 ../scripts/add_android_flavors.py .
Backs up gradle file before editing.
"""
import sys
from pathlib import Path

root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
p=root/'android/app/build.gradle.kts'
if not p.exists():
    sys.exit('Missing android/app/build.gradle.kts. Run flutter create --platforms=android . first.')
s=p.read_text()
if 'create("direct")' in s and 'create("play")' in s:
    print('Flavors already configured:',p)
    sys.exit(0)
needle='android {'
if needle not in s:
    sys.exit('Could not find standard android { block; configure flavors manually.')
flavors='''android {
    flavorDimensions += "distribution"
    productFlavors {
        create("play") {
            dimension = "distribution"
        }
        create("direct") {
            dimension = "distribution"
            applicationIdSuffix = ".direct"
            versionNameSuffix = "-direct"
        }
    }
'''
backup=p.with_suffix('.kts.before-kisa-flavors')
backup.write_text(s)
p.write_text(s.replace(needle,flavors,1))
print('Added play and direct product flavors. Backup:',backup)
print('Run: flutter build appbundle --flavor play --release ...')
print('Or:  flutter build apk --flavor direct --release ...')
