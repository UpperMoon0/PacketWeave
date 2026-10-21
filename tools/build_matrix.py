#!/usr/bin/env python3
"""Build native mod jars with independent Forge/Fabric/NeoForge Gradle installations."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
from release_contract import TARGETS as TARGET_MATRIX
TARGETS = [item["target"] for item in TARGET_MATRIX]
def command_for(target, task):
    if target not in TARGETS: raise ValueError(target)
    root=ROOT/"targets"/target
    wrapper=root/("gradlew.bat" if os.name=="nt" else "gradlew")
    return [str(wrapper),task,"--no-daemon","--stacktrace"]
def environment_for(target, current=None):
    environment = dict(os.environ if current is None else current)
    runtime = next(item["java"] for item in TARGET_MATRIX if item["target"] == target)
    home = environment.get("JAVA" + runtime + "_HOME") or environment.get("JAVA_HOME_" + runtime + "_X64")
    if home:
        environment["JAVA_HOME"] = home
        environment["PATH"] = str(Path(home)/"bin") + os.pathsep + environment.get("PATH", "")
    return environment

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
            rc=subprocess.call(cmd,cwd=str(ROOT/"targets"/target),env=environment_for(target))
            if rc: return rc
    return 0
if __name__=="__main__":sys.exit(main())
