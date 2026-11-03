import json
import pytest
from autoclip.pipeline.editorial import Assessment, rejection, review
from autoclip.pipeline.transcript import Transcript, Word
from autoclip.db.models import Clip
from autoclip.providers import DetectionConfig


def assessment(**changes):
    return Assessment(**(dict(hook=5, context=5, payoff=5, specificity=5, complete=True,
        opening_quote='Why leave', payoff_quote='found peace', reason='A complete answer.') | changes))


@pytest.mark.parametrize('changes', [dict(complete=False), dict(payoff=2),
    dict(opening_quote='invented opening'), dict(payoff_quote='invented ending')])
def test_high_score_cannot_override_missing_story_or_evidence(changes):
    assert rejection(assessment(**changes), 'Why leave today I finally found peace', 75)


def test_grounded_review_and_threshold():
    assert not rejection(assessment(), 'Why leave today I finally found peace', 75)
    assert rejection(assessment(hook=3, context=3, payoff=3, specificity=3),
                     'Why leave today I finally found peace', 75)


@pytest.mark.asyncio
async def test_review_cache_quota_and_failure_report(tmp_path):
    class Provider:
        name, model, base_url = 'ollama', 'test', 'local'
        calls = 0
        async def _complete(self, *args):
            self.calls += 1
            return assessment().model_dump_json()
    provider = Provider()
    transcript = Transcript(words=[Word(w, i, i+1) for i,w in enumerate('Why leave today I finally found peace'.split())])
    clip = Clip(id='c', job_id='j', start_s=0, end_s=7, start_word=0, end_word=6)
    settings = DetectionConfig(quality_review=True, max_clips=3)
    options = dict(cache_dir=tmp_path/'cache', report_path=tmp_path/'report.json')
    for _ in range(2):
        result = await review([clip], transcript, provider, settings, **options)
        assert len(result) == 1 and result[0].score == 100
    assert provider.calls == 1
    assert json.loads((tmp_path/'report.json').read_text())['clips'][0]['status'] == 'approved'
    provider.model = 'different'
    async def fail(*args): raise RuntimeError('offline')
    provider._complete = fail
    with pytest.raises(RuntimeError, match='offline'):
        await review([clip], transcript, provider, settings, **options)
    assert json.loads((tmp_path/'report.json').read_text())['clips'][0]['status'] == 'error'
