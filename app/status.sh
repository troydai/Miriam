#!/usr/bin/env bash

# enter virtualenv
. $AZ_BATCH_NODE_SHARED_DIR/venv/bin/activate

pip list --format=columns
nosetests azure --collect-only -v
