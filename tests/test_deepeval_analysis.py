"""DeepEval quality tests for ITP analytical outputs.

These tests use DeepEval metrics with a local Ollama judge model to evaluate
the quality of baft analytical pipeline outputs. They require:
- deepeval package installed (uv sync --extra eval)
- Ollama running locally with command-r7b model

Run: uv run pytest tests/test_deepeval_analysis.py -v
Skip: uv run pytest tests/ -m "not deepeval"
"""
import pytest
from tests.conftest import skip_no_deepeval

pytestmark = [pytest.mark.deepeval, skip_no_deepeval]

@pytest.fixture(scope="module")
def judge_model():
    from deepeval.models import OllamaModel
    return OllamaModel(
        model="command-r7b:latest",
        base_url="http://localhost:11434",
    )

@pytest.fixture(scope="module")
def claim_extraction_quality(judge_model):
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams
    return GEval(
        name="Claim Extraction Quality",
        criteria=(
            "The extracted claims must be factual statements present in or "
            "derivable from the source text, with appropriate epistemic tags "
            "(fact/inference/uncertain/speculation) and source attribution."
        ),
        evaluation_steps=[
            "Check each extracted claim appears in or is derivable from the input.",
            "Verify epistemic tags match the certainty level of the source.",
            "Confirm source_tier assignment is plausible.",
        ],
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=judge_model,
        threshold=0.6,
    )

@pytest.fixture(scope="module")
def synthesis_faithfulness(judge_model):
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams
    return GEval(
        name="Synthesis Faithfulness",
        criteria=(
            "The synthesis must faithfully represent the analytical inputs "
            "without adding unsupported claims or omitting key findings."
        ),
        evaluation_steps=[
            "Check that major findings from the input are represented.",
            "Verify no claims appear that are not supported by the input.",
            "Confirm the synthesis maintains appropriate hedging language.",
        ],
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=judge_model,
        threshold=0.6,
    )

def test_sp_claim_extraction(judge_model, claim_extraction_quality):
    """SP worker should extract relevant claims with proper epistemic tagging."""
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase

    test_case = LLMTestCase(
        input=(
            "Iranian state media reported that the Central Bank announced a "
            "new currency stabilization program. Analysts suggest this may "
            "reduce inflation by 2-3 percentage points over the next quarter, "
            "though some economists remain skeptical about its effectiveness."
        ),
        actual_output=(
            '{"claims": ['
            '  {"text": "Central Bank announced currency stabilization program", '
            '   "epistemic_tag": "fact", "source_tier": 2},'
            '  {"text": "Program may reduce inflation by 2-3 percentage points", '
            '   "epistemic_tag": "inference", "source_tier": 3},'
            '  {"text": "Some economists skeptical about effectiveness", '
            '   "epistemic_tag": "uncertain", "source_tier": 3}'
            ']}'
        ),
    )
    assert_test(test_case, [claim_extraction_quality])

def test_as_synthesis_faithfulness(judge_model, synthesis_faithfulness):
    """AS synthesis should faithfully represent audit node outputs."""
    from deepeval import assert_test
    from deepeval.test_case import LLMTestCase

    test_case = LLMTestCase(
        input=(
            "Logical Analysis: Claims are internally consistent. "
            "The currency program announcement is well-documented. "
            "Predictive Analysis: Similar programs in 2019 and 2022 achieved "
            "partial success (1.5% reduction vs 2-3% projected). "
            "Red Team: Alternative explanation — program may be primarily "
            "political signaling ahead of elections rather than economic policy."
        ),
        actual_output=(
            "The currency stabilization program is well-documented and internally "
            "consistent. Historical precedent suggests partial effectiveness, with "
            "past programs achieving roughly half their projected targets. However, "
            "the timing raises the possibility of political motivation alongside "
            "genuine economic intent."
        ),
    )
    assert_test(test_case, [synthesis_faithfulness])
