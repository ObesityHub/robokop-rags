#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export RAGS_HOME="$DIR/.."
if [ "$DEPLOY" != "docker" ]; then
    export $(cat $RAGS_HOME/rags.env | grep -v ^# | xargs)
fi