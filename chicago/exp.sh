#!/bin/sh
# usage: exp.sh <spot> <experiments> [key=value ...]
# Queue a capture of <spot> with a converter variant (CHI_EXPERIMENT=<experiments>) in the lab.
# The old version depended on scripts in a deleted session scratchpad; lab.py caches the
# variant as work/var_<hash>.lev and runs it on a devtest slot. Results: devtest/_lab/events.log.
set -e
cd "$(dirname "$0")"
spot="$1"; exp="$2"; shift 2
python devtools/lab.py add capture "$spot" "experiment=$exp" "$@"
python devtools/lab.py status | head -3
