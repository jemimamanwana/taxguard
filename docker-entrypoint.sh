#!/bin/sh
set -e
# First run: generate synthetic data, load + score it, run the evaluation.
if [ ! -f data/claims.csv ]; then python -m data_gen.generate; fi
if [ "${LL_RESEED:-1}" = "1" ]; then python -m api.app.seed && python -m eval.run_eval; fi
exec uvicorn api.app.main:app --host 0.0.0.0 --port 8000
