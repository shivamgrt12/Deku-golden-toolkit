ARG BASE
FROM ${BASE}
COPY tests/ /tests/
COPY golden/ /golden/
RUN chmod +x /tests/test.sh /tests/score.py /tests/run_workflows.py /tests/run_rubric.py /tests/run_rewardkit.py \
 && mkdir -p /golden/suite /logs/golden \
 && cp /golden/probes/golden_conftest.py /golden/suite/conftest.py
WORKDIR /tests
