#!/usr/bin/env python3
"""Build native mod jars with independent Forge/Fabric/NeoForge Gradle installations."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
TARGETS=[
"fabric-1.16.5","forge-1.16.5",
"fabric-1.20.1","forge-1.20.1",
"fabric-1.21.1","neoforge-1.21.1",
"fabric-26.1.2","neoforge-26.1.2",
]
def command_for(target, task):
    if target not in TARGETS: raise ValueError(target)
    root=ROOT/"targets"/target
    wrapper=root/("gradlew.bat" if os.name=="nt" else "gradlew")
    return [str(wrapper),task,"--no-daemon","--stacktrace"]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("task",choices=("build","test","compileJava","tasks"),nargs="?",default="build")
    parser.add_argument("--target",choices=TARGETS)
    parser.add_argument("--all",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    if not args.all and not args.target:parser.error("specify --target or --all")
    for target in (TARGETS if args.all else [args.target]):
        cmd=command_for(target,args.task)
        print(target, " ".join(cmd),flush=True)
        if not args.dry_run:
            rc=subprocess.call(cmd,cwd=str(ROOT/"targets"/target))
            if rc: return rc
    return 0
if __name__=="__main__":sys.exit(main())
